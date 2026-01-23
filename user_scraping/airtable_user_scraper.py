#!/usr/bin/env python3
"""
Airtable Base User Scraper

Scrapes user access data from Airtable bases by intercepting the 
window.resolveLiveappDataPromise() initialization call.

Usage:
    1. First run: python airtable_user_scraper.py --login
       (Opens browser for manual login, saves auth state)
    2. Subsequent runs: python airtable_user_scraper.py
       (Uses saved auth to scrape all bases)

Requirements:
    pip install playwright aiohttp --break-system-packages
    playwright install chromium
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext


# Configuration
OUTPUT_DIR = Path("output")
AUTH_STATE_FILE = OUTPUT_DIR / "airtable_auth_state.json"
OUTPUT_FILE = OUTPUT_DIR / "airtable_users_export.json"
CONFIG_FILE = OUTPUT_DIR / "airtable_scraper_config.json"
DEBUG_DIR = OUTPUT_DIR / "debug"
AIRTABLE_API_KEY_ENV = "AIRTABLE_API_KEY"  # Optional: for fetching base list


@dataclass
class UserInfo:
    """Represents a user with access to a base."""
    id: str
    email: str
    first_name: str
    last_name: str
    permission_level: str = "unknown"
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.full_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "permission_level": self.permission_level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserInfo":
        return cls(
            id=data["id"],
            email=data["email"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            permission_level=data.get("permission_level", "unknown"),
        )


@dataclass
class BaseAccessReport:
    """Represents access information for a single base."""
    base_id: str
    base_name: str
    workspace_id: str
    workspace_name: str
    users: list[UserInfo] = field(default_factory=list)
    scrape_time: str = field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "base_id": self.base_id,
            "base_name": self.base_name,
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "users": [u.to_dict() for u in self.users],
            "user_count": len(self.users),
            "scrape_time": self.scrape_time,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BaseAccessReport":
        users = [UserInfo.from_dict(u) for u in data.get("users", [])]
        return cls(
            base_id=data["base_id"],
            base_name=data["base_name"],
            workspace_id=data.get("workspace_id", "Unknown"),
            workspace_name=data.get("workspace_name", "Unknown"),
            users=users,
            scrape_time=data.get("scrape_time", ""),
            error=data.get("error"),
        )


def load_reports_from_json(json_path: Path) -> list[BaseAccessReport]:
    """Load BaseAccessReport objects from a JSON export file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [BaseAccessReport.from_dict(b) for b in data.get("bases", [])]


class AirtableScraper:
    """
    Scrapes user access data from Airtable bases.

    The scraper works by awaiting window.liveappDataPromise, which Airtable
    creates and resolves with initialization data when loading a base.
    This promise resolves to a JSON payload containing:
    - rawUsers: all users with access to workspace/base
    - collaboratorsByWorkspaceId: permission mappings at workspace level
    - collaboratorsByApplicationId: permission mappings at base level
    - rawWorkspaces: workspace metadata
    - rawApplications: base metadata
    """
    
    def __init__(
        self,
        headless: bool = True,
        debug: bool = False,
        context_recycle_interval: int = 15,
        max_retries: int = 3,
    ):
        self.headless = headless
        self.debug = debug
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.captured_data: dict = {}
        self.context_recycle_interval = context_recycle_interval
        self.max_retries = max_retries
        self._requests_since_recycle = 0
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        await self.playwright.stop()
    
    async def login_and_save_auth(self) -> None:
        """
        Opens a browser for manual login, then saves the auth state.
        User must log in manually and navigate to any base.
        """
        print("Opening browser for login...")
        print("Please log in to Airtable, then press Enter in this terminal.")
        
        # Non-headless for manual login
        context = await self.browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://airtable.com/login")
        
        input("Press Enter after you've logged in and can see your bases...")
        
        # Save auth state
        await context.storage_state(path=str(AUTH_STATE_FILE))
        print(f"Auth state saved to {AUTH_STATE_FILE}")
        
        await context.close()
    
    async def load_auth(self) -> BrowserContext:
        """Loads saved auth state into a new browser context."""
        if not AUTH_STATE_FILE.exists():
            raise FileNotFoundError(
                f"Auth state file not found: {AUTH_STATE_FILE}\n"
                "Run with --login first to authenticate."
            )
        
        self.context = await self.browser.new_context(
            storage_state=str(AUTH_STATE_FILE)
        )
        return self.context

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is transient and worth retrying."""
        error_str = str(error).lower()
        retryable_patterns = [
            "timeout",
            "net::err_connection",
            "net::err_network",
            "net::err_aborted",
            "navigation failed",
            "page crashed",
            "context closed",
            "target closed",
            "session closed",
            "rate limit",
            "429",
            "503",
            "502",
        ]
        return any(pattern in error_str for pattern in retryable_patterns)

    async def _maybe_recycle_context(self) -> None:
        """Recycle browser context periodically to prevent resource exhaustion."""
        self._requests_since_recycle += 1

        if self._requests_since_recycle >= self.context_recycle_interval:
            if self.context:
                print("  [Recycling browser context...]")
                await self.context.close()
                self.context = None
            self._requests_since_recycle = 0
            await self.load_auth()

    async def scrape_base(self, base_id: str) -> BaseAccessReport:
        """
        Scrapes user access data from a single base with retry logic.

        Args:
            base_id: Airtable base ID (e.g., 'appXXXXXXXXXXXXXX')

        Returns:
            BaseAccessReport with all users who have access
        """
        if not self.context:
            await self.load_auth()

        await self._maybe_recycle_context()

        last_error = None
        initial_backoff = 2.0
        backoff_multiplier = 2.0
        max_backoff = 30.0
        backoff = initial_backoff

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                print(f"  Retry {attempt}/{self.max_retries} after {backoff:.1f}s backoff...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * backoff_multiplier, max_backoff)

            page = await self.context.new_page()
            self.captured_data = {}

            try:
                url = f"https://airtable.com/{base_id}"
                if attempt == 0:
                    print(f"  Loading {url}...")

                # Use domcontentloaded instead of networkidle - more reliable for JS-heavy apps
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Wait for the liveappDataPromise with explicit timeout
                # This is more reliable than networkidle for complex JS apps
                self.captured_data = await page.evaluate("""
                    () => {
                        return Promise.race([
                            window.liveappDataPromise,
                            new Promise((_, reject) =>
                                setTimeout(() => reject(new Error('liveappDataPromise timeout')), 25000)
                            )
                        ]);
                    }
                """)

                if not self.captured_data:
                    # Fallback: try to extract from page source
                    self.captured_data = await self._extract_from_source(page)

                if not self.captured_data:
                    # Debug mode: save diagnostic info
                    if self.debug:
                        await self._save_debug_info(page, base_id)

                    return BaseAccessReport(
                        base_id=base_id,
                        base_name="Unknown",
                        workspace_id="Unknown",
                        workspace_name="Unknown",
                        error="Failed to capture initialization data"
                    )

                return self._parse_access_data(base_id, self.captured_data)

            except Exception as e:
                last_error = str(e)
                is_retryable = self._is_retryable_error(e)

                if not is_retryable or attempt >= self.max_retries:
                    return BaseAccessReport(
                        base_id=base_id,
                        base_name="Unknown",
                        workspace_id="Unknown",
                        workspace_name="Unknown",
                        error=f"{'(after retries) ' if attempt > 0 else ''}{last_error}"
                    )

                print(f"  Transient error: {last_error}")

            finally:
                await page.close()

        # Should not reach here, but just in case
        return BaseAccessReport(
            base_id=base_id,
            base_name="Unknown",
            workspace_id="Unknown",
            workspace_name="Unknown",
            error=last_error or "Unknown error"
        )
    
    async def _extract_from_source(self, page: Page) -> Optional[dict]:
        """
        Fallback: extract init data from page HTML source.
        Looks for window.resolveLiveappDataPromise({...}) in script tags.
        """
        content = await page.content()
        
        # Find the function call in the HTML
        pattern = r'window\.resolveLiveappDataPromise\((\{.*?\})\);'
        
        # This is tricky because the JSON can be huge and span lines
        # Try a different approach: find the script and parse it
        match = re.search(
            r'window\.resolveLiveappDataPromise\((.*?)\);?\s*<\/script>',
            content,
            re.DOTALL
        )
        
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    async def _save_debug_info(self, page: Page, base_id: str) -> None:
        """
        Save diagnostic information when data capture fails.
        Helps identify the current Airtable initialization pattern.
        """
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

        # 1. Save page HTML
        content = await page.content()
        html_path = DEBUG_DIR / f"{base_id}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  [DEBUG] Saved HTML to {html_path}")

        # 2. Find relevant window globals
        globals_info = await page.evaluate("""
            () => {
                const relevant = Object.keys(window).filter(k => {
                    const lower = k.toLowerCase();
                    return lower.includes('resolve') ||
                           lower.includes('liveapp') ||
                           lower.includes('init') ||
                           lower.includes('airtable') ||
                           lower.includes('data');
                });
                return relevant;
            }
        """)
        print(f"  [DEBUG] Relevant window globals: {globals_info}")

        # 3. Search for data patterns in scripts
        script_info = await page.evaluate("""
            () => {
                const patterns = ['rawUsers', 'collaborators', 'rawApplications', 'rawWorkspaces'];
                const results = {};
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.textContent || '';
                    for (const p of patterns) {
                        if (text.includes(p)) {
                            // Find the context around this pattern
                            const idx = text.indexOf(p);
                            const start = Math.max(0, idx - 50);
                            const end = Math.min(text.length, idx + 100);
                            results[p] = text.substring(start, end);
                        }
                    }
                }
                return results;
            }
        """)
        if script_info:
            print(f"  [DEBUG] Found data patterns in scripts:")
            for pattern, context in script_info.items():
                print(f"    - {pattern}: ...{context}...")
        else:
            print("  [DEBUG] No data patterns found in inline scripts")

        # 4. Check for any __NEXT_DATA__ or similar embedded JSON
        embedded_json = await page.evaluate("""
            () => {
                // Check for Next.js data
                const nextData = document.getElementById('__NEXT_DATA__');
                if (nextData) {
                    return { type: '__NEXT_DATA__', preview: nextData.textContent.substring(0, 500) };
                }
                // Check for other common patterns
                const scripts = document.querySelectorAll('script[type="application/json"]');
                for (const s of scripts) {
                    if (s.textContent && s.textContent.length > 100) {
                        return { type: 'application/json script', preview: s.textContent.substring(0, 500) };
                    }
                }
                return null;
            }
        """)
        if embedded_json:
            print(f"  [DEBUG] Found embedded JSON ({embedded_json['type']}):")
            print(f"    {embedded_json['preview'][:200]}...")

        # 5. Save full debug report
        report_path = DEBUG_DIR / f"{base_id}_report.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"Debug Report for {base_id}\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Window globals: {globals_info}\n\n")
            f.write(f"Script patterns: {json.dumps(script_info, indent=2)}\n\n")
            f.write(f"Embedded JSON: {json.dumps(embedded_json, indent=2)}\n")
        print(f"  [DEBUG] Full report saved to {report_path}")

    def _parse_access_data(self, base_id: str, data: dict) -> BaseAccessReport:
        """
        Parses the captured initialization data to extract user access info.
        
        The data structure is:
        - rawApplications: {base_id: {name, ...}}
        - rawWorkspaces: {workspace_id: {name, ...}}
        - rawUsers: {user_id: {email, firstName, lastName, ...}}
        - collaboratorsByWorkspaceId: {workspace_id: [{userId, permissionLevel}, ...]}
        - collaboratorsByApplicationId: {base_id: [{userId, permissionLevel}, ...]}
        """
        # Get base metadata
        raw_apps = data.get("rawApplications", {})
        app_info = raw_apps.get(base_id, {})
        base_name = app_info.get("name", "Unknown")
        
        # Get workspace info
        raw_workspaces = data.get("rawWorkspaces", {})
        workspace_id = "Unknown"
        workspace_name = "Unknown"
        
        # Find which workspace this base belongs to
        for ws_id, ws_data in raw_workspaces.items():
            if ws_id == "wspSHARED00000000":
                continue  # Skip "shared with me" pseudo-workspace
            visible_apps = ws_data.get("visibleApplicationOrder", [])
            if base_id in visible_apps:
                workspace_id = ws_id
                workspace_name = ws_data.get("name", "Unknown")
                break
        
        # Get all users
        raw_users = data.get("rawUsers", {})
        
        # Get collaborators (both workspace-level and base-level)
        workspace_collaborators = data.get("collaboratorsByWorkspaceId", {}).get(
            workspace_id, []
        )
        base_collaborators = data.get("collaboratorsByApplicationId", {}).get(
            base_id, []
        )
        
        # Build user permission map (base-level overrides workspace-level)
        user_permissions: dict[str, str] = {}
        
        for collab in workspace_collaborators:
            if collab.get("type") == 0:  # User type
                user_id = collab.get("userId")
                if user_id:
                    user_permissions[user_id] = collab.get("permissionLevel", "unknown")
        
        for collab in base_collaborators:
            if collab.get("type") == 0:  # User type
                user_id = collab.get("userId")
                if user_id:
                    user_permissions[user_id] = collab.get("permissionLevel", "unknown")
        
        # Build user list
        users = []
        for user_id, permission in user_permissions.items():
            user_data = raw_users.get(user_id, {})
            
            # Skip service accounts
            if user_data.get("isServiceAccount"):
                continue
            if user_id in ("usrAISERVICE00000", "usrEXTERNALTBLSVC", "usrWORKFLOWEXESVC"):
                continue
            
            users.append(UserInfo(
                id=user_id,
                email=user_data.get("email", ""),
                first_name=user_data.get("firstName", ""),
                last_name=user_data.get("lastName", ""),
                permission_level=permission,
            ))
        
        # Sort by email for consistent output
        users.sort(key=lambda u: u.email.lower())
        
        return BaseAccessReport(
            base_id=base_id,
            base_name=base_name,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            users=users,
        )
    
    async def scrape_multiple_bases(
        self,
        base_ids: list[str],
        delay_seconds: float = 1.0,
        error_delay_multiplier: float = 2.0,
        max_delay_seconds: float = 10.0,
    ) -> list[BaseAccessReport]:
        """
        Scrapes multiple bases with adaptive delays between requests.

        Args:
            base_ids: List of Airtable base IDs
            delay_seconds: Base delay between scraping each base
            error_delay_multiplier: Multiply delay by this factor after errors
            max_delay_seconds: Maximum delay between requests

        Returns:
            List of BaseAccessReport objects
        """
        reports = []
        total = len(base_ids)
        current_delay = delay_seconds
        consecutive_errors = 0

        for i, base_id in enumerate(base_ids, 1):
            print(f"[{i}/{total}] Scraping base {base_id}...")
            report = await self.scrape_base(base_id)
            reports.append(report)

            if report.error:
                print(f"  Error: {report.error}")
                consecutive_errors += 1
                # Increase delay after errors
                current_delay = min(
                    current_delay * error_delay_multiplier,
                    max_delay_seconds
                )
                print(f"  Increasing delay to {current_delay:.1f}s")
            else:
                print(f"  Found {len(report.users)} users in '{report.base_name}'")
                consecutive_errors = 0
                # Gradually return to base delay after successes
                if current_delay > delay_seconds:
                    current_delay = max(delay_seconds, current_delay / error_delay_multiplier)

            # Warn after many consecutive errors
            if consecutive_errors >= 5:
                print(f"\n  WARNING: {consecutive_errors} consecutive errors!")
                print("  This might indicate rate limiting or session expiry.")
                print("  Consider: Re-running with --login or waiting before continuing.\n")

            if i < total:
                await asyncio.sleep(current_delay)

        return reports


async def fetch_base_ids_from_api() -> list[str]:
    """
    Fetches list of base IDs from Airtable API.
    Requires AIRTABLE_API_KEY environment variable.
    """
    api_key = os.environ.get(AIRTABLE_API_KEY_ENV)
    if not api_key:
        raise ValueError(
            f"Set {AIRTABLE_API_KEY_ENV} environment variable to fetch base list, "
            "or provide base IDs directly."
        )
    
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {api_key}"}
        bases = []
        offset = None
        
        while True:
            url = "https://api.airtable.com/v0/meta/bases"
            if offset:
                url += f"?offset={offset}"
            
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                bases.extend(data.get("bases", []))
                offset = data.get("offset")
                
                if not offset:
                    break
        
        return [b["id"] for b in bases]


def export_aggregated_csvs(reports: list[BaseAccessReport]):
    """
    Export aggregated CSV files per workspace:
    - {workspace}_users.csv - One row per user, columns for each permission level with base names
    - {workspace}_bases.csv - One row per base, columns for each permission level with user emails
    """
    import csv

    permission_levels = ["owner", "create", "edit", "comment", "read"]

    # Group reports by workspace
    by_workspace: dict[str, list[BaseAccessReport]] = {}
    for report in reports:
        if report.error:
            continue
        ws_key = report.workspace_id or "Unknown"
        if ws_key not in by_workspace:
            by_workspace[ws_key] = []
        by_workspace[ws_key].append(report)

    files_created = []

    for ws_id, ws_reports in by_workspace.items():
        ws_name = ws_reports[0].workspace_name or "Unknown"

        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in ws_name)
        safe_name = safe_name.replace(" ", "_")

        # Build user-centric data for this workspace
        users_data: dict[str, dict] = {}
        # Build base-centric data for this workspace
        bases_data: dict[str, dict] = {}

        for report in ws_reports:
            base_id = report.base_id
            base_name = report.base_name

            # Initialize base entry
            if base_id not in bases_data:
                bases_data[base_id] = {
                    "base_name": base_name,
                    "permissions": {level: [] for level in permission_levels}
                }

            for user in report.users:
                user_id = user.id
                email = user.email
                name = user.full_name
                permission = user.permission_level

                # Initialize user entry
                if user_id not in users_data:
                    users_data[user_id] = {
                        "name": name,
                        "email": email,
                        "permissions": {level: [] for level in permission_levels}
                    }

                # Add base to user's permission list
                if permission in permission_levels:
                    users_data[user_id]["permissions"][permission].append(base_name)
                    bases_data[base_id]["permissions"][permission].append(email)

        # Calculate total bases per user
        total_bases_in_workspace = len(bases_data)
        for user_id, data in users_data.items():
            total = sum(len(data["permissions"][level]) for level in permission_levels)
            data["total_bases"] = total

        # Find workspace-wide users (those with access to ALL bases)
        workspace_wide_emails = {
            data["email"] for _, data in users_data.items()
            if data["total_bases"] == total_bases_in_workspace
        }

        # Calculate total users per base and base-specific users
        for base_id, data in bases_data.items():
            all_emails = set()
            for level in permission_levels:
                all_emails.update(data["permissions"][level])
            data["total_users"] = len(all_emails)
            # Base-specific = users who are NOT workspace-wide
            base_specific_emails = all_emails - workspace_wide_emails
            data["base_specific_users_count"] = len(base_specific_emails)
            data["base_specific_users_list"] = sorted(base_specific_emails)

        # Write users CSV for this workspace (sorted by total_bases descending)
        users_csv_path = OUTPUT_DIR / f"{safe_name}_users.csv"
        with open(users_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "user_id", "name", "email", "total_bases",
                "owner_bases", "create_bases", "edit_bases", "comment_bases", "read_bases"
            ])

            for user_id, data in sorted(users_data.items(), key=lambda x: -x[1]["total_bases"]):
                writer.writerow([
                    user_id,
                    data["name"],
                    data["email"],
                    data["total_bases"],
                    ", ".join(sorted(data["permissions"]["owner"])),
                    ", ".join(sorted(data["permissions"]["create"])),
                    ", ".join(sorted(data["permissions"]["edit"])),
                    ", ".join(sorted(data["permissions"]["comment"])),
                    ", ".join(sorted(data["permissions"]["read"])),
                ])

        # Write bases CSV for this workspace (sorted by total_users descending)
        bases_csv_path = OUTPUT_DIR / f"{safe_name}_bases.csv"
        with open(bases_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "base_id", "base_name", "total_users", "base_specific_count", "base_specific_users",
                "owner_users", "create_users", "edit_users", "comment_users", "read_users"
            ])

            for base_id, data in sorted(bases_data.items(), key=lambda x: -x[1]["total_users"]):
                writer.writerow([
                    base_id,
                    data["base_name"],
                    data["total_users"],
                    data["base_specific_users_count"],
                    ", ".join(data["base_specific_users_list"]),
                    ", ".join(sorted(data["permissions"]["owner"])),
                    ", ".join(sorted(data["permissions"]["create"])),
                    ", ".join(sorted(data["permissions"]["edit"])),
                    ", ".join(sorted(data["permissions"]["comment"])),
                    ", ".join(sorted(data["permissions"]["read"])),
                ])

        files_created.append((ws_name, len(users_data), len(bases_data)))
        print(f"Exported {users_csv_path} ({len(users_data)} users)")
        print(f"Exported {bases_csv_path} ({len(bases_data)} bases)")

    return files_created


def generate_workspace_summary(reports: list[BaseAccessReport]) -> dict:
    """
    Generate a summary report grouped by workspace.
    
    Returns dict with per-workspace stats:
    - Base count
    - User count (unique per workspace)
    - Permission breakdown
    """
    summary = {}
    
    for report in reports:
        if report.error:
            continue
        
        ws_id = report.workspace_id or "unknown"
        
        if ws_id not in summary:
            summary[ws_id] = {
                "workspace_id": ws_id,
                "workspace_name": report.workspace_name,
                "bases": [],
                "users": {},  # email -> {bases: [], permissions: set()}
            }
        
        ws = summary[ws_id]
        ws["bases"].append({
            "base_id": report.base_id,
            "base_name": report.base_name,
            "user_count": len(report.users),
        })
        
        for user in report.users:
            if user.email not in ws["users"]:
                ws["users"][user.email] = {
                    "name": user.full_name,
                    "bases": [],
                    "permissions": set(),
                }
            ws["users"][user.email]["bases"].append(report.base_id)
            ws["users"][user.email]["permissions"].add(user.permission_level)
    
    # Convert to serializable format and add stats
    result = {}
    for ws_id, ws in summary.items():
        users_list = []
        for email, data in ws["users"].items():
            users_list.append({
                "email": email,
                "name": data["name"],
                "base_count": len(data["bases"]),
                "permissions": list(data["permissions"]),
            })
        users_list.sort(key=lambda u: u["email"])
        
        result[ws_id] = {
            "workspace_id": ws_id,
            "workspace_name": ws["workspace_name"],
            "base_count": len(ws["bases"]),
            "unique_user_count": len(users_list),
            "bases": ws["bases"],
            "users": users_list,
        }
    
    return result


def print_workspace_summary(reports: list[BaseAccessReport]) -> None:
    """Print a formatted workspace summary to console."""
    summary = generate_workspace_summary(reports)
    
    print("\n" + "=" * 60)
    print("WORKSPACE SUMMARY")
    print("=" * 60)
    
    for ws_id, ws in summary.items():
        print(f"\n📁 {ws['workspace_name']} ({ws_id})")
        print(f"   Bases: {ws['base_count']}")
        print(f"   Unique users: {ws['unique_user_count']}")
        
        # Permission breakdown
        perm_counts = {}
        for user in ws["users"]:
            for perm in user["permissions"]:
                perm_counts[perm] = perm_counts.get(perm, 0) + 1
        
        if perm_counts:
            perm_str = ", ".join(f"{p}: {c}" for p, c in sorted(perm_counts.items()))
            print(f"   Permissions: {perm_str}")


def load_config() -> dict:
    """
    Load configuration from config file.
    
    Config structure:
    {
        "workspaces": {
            "wspXXX": {
                "name": "Workspace Name",
                "base_ids": ["app1", "app2", ...]
            },
            ...
        }
    }
    """
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"workspaces": {}}


def save_config(config: dict) -> None:
    """Save configuration to config file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Config saved to {CONFIG_FILE}")


def get_all_base_ids(config: dict) -> list[str]:
    """Extract flat list of all base IDs from config."""
    base_ids = []
    for ws_data in config.get("workspaces", {}).values():
        base_ids.extend(ws_data.get("base_ids", []))
    return base_ids


def get_workspace_base_ids(config: dict, workspace_filter: list[str]) -> list[str]:
    """Get base IDs for specific workspaces (by ID or name)."""
    base_ids = []
    workspaces = config.get("workspaces", {})
    
    for ws_id, ws_data in workspaces.items():
        ws_name = ws_data.get("name", "")
        # Match by ID or name (case-insensitive)
        if ws_id in workspace_filter or ws_name.lower() in [w.lower() for w in workspace_filter]:
            base_ids.extend(ws_data.get("base_ids", []))
    
    return base_ids


def update_config_from_reports(config: dict, reports: list[BaseAccessReport]) -> dict:
    """
    Update config with workspace info learned from scraping.
    Groups bases by their workspace.
    """
    workspaces = config.get("workspaces", {})
    
    for report in reports:
        if report.error:
            continue

        ws_id = report.workspace_id or "Unknown"

        if ws_id not in workspaces:
            workspaces[ws_id] = {
                "name": report.workspace_name,
                "base_ids": []
            }
        
        # Update workspace name if we have a better one
        if report.workspace_name and report.workspace_name != "Unknown":
            workspaces[ws_id]["name"] = report.workspace_name
        
        # Add base if not already present
        if report.base_id not in workspaces[ws_id]["base_ids"]:
            workspaces[ws_id]["base_ids"].append(report.base_id)
    
    config["workspaces"] = workspaces
    return config


def print_config_summary(config: dict) -> None:
    """Print a summary of configured workspaces and bases."""
    workspaces = config.get("workspaces", {})
    
    if not workspaces:
        print("No workspaces configured.")
        return
    
    print(f"\nConfigured workspaces ({len(workspaces)}):")
    for ws_id, ws_data in workspaces.items():
        name = ws_data.get("name", "Unknown")
        bases = ws_data.get("base_ids", [])
        print(f"  {name} ({ws_id}): {len(bases)} bases")


def compare_reports(old_file: Path, new_reports: list[BaseAccessReport]) -> dict:
    """
    Compare new results with previous run to identify changes.
    
    Returns dict with:
    - added_users: users who gained access
    - removed_users: users who lost access  
    - permission_changes: users whose permissions changed
    - new_bases: bases not in previous run
    """
    changes = {
        "added_users": [],
        "removed_users": [],
        "permission_changes": [],
        "new_bases": [],
        "removed_bases": [],
    }
    
    if not old_file.exists():
        return changes
    
    with open(old_file, "r") as f:
        old_data = json.load(f)
    
    old_bases = {b["base_id"]: b for b in old_data.get("bases", [])}
    new_bases = {r.base_id: r for r in new_reports}
    
    # Find new/removed bases
    for base_id in new_bases:
        if base_id not in old_bases:
            changes["new_bases"].append(base_id)
    
    for base_id in old_bases:
        if base_id not in new_bases:
            changes["removed_bases"].append(base_id)
    
    # Compare users per base
    for base_id, new_report in new_bases.items():
        if base_id not in old_bases:
            continue
        
        old_base = old_bases[base_id]
        old_users = {u["email"]: u for u in old_base.get("users", [])}
        new_users = {u.email: u for u in new_report.users}
        
        base_name = new_report.base_name
        
        # Added users
        for email in new_users:
            if email not in old_users:
                changes["added_users"].append({
                    "base_id": base_id,
                    "base_name": base_name,
                    "email": email,
                    "name": new_users[email].full_name,
                    "permission": new_users[email].permission_level,
                })
        
        # Removed users
        for email in old_users:
            if email not in new_users:
                changes["removed_users"].append({
                    "base_id": base_id,
                    "base_name": base_name,
                    "email": email,
                    "name": old_users[email].get("name", ""),
                })
        
        # Permission changes
        for email in new_users:
            if email in old_users:
                old_perm = old_users[email].get("permission_level", "")
                new_perm = new_users[email].permission_level
                if old_perm != new_perm:
                    changes["permission_changes"].append({
                        "base_id": base_id,
                        "base_name": base_name,
                        "email": email,
                        "old_permission": old_perm,
                        "new_permission": new_perm,
                    })
    
    return changes


def print_changes(changes: dict) -> None:
    """Print a summary of changes from previous run."""
    print("\n" + "=" * 50)
    print("CHANGES SINCE LAST RUN")
    print("=" * 50)
    
    if changes["new_bases"]:
        print(f"\n📦 New bases ({len(changes['new_bases'])}):")
        for base_id in changes["new_bases"]:
            print(f"  + {base_id}")
    
    if changes["removed_bases"]:
        print(f"\n📦 Removed bases ({len(changes['removed_bases'])}):")
        for base_id in changes["removed_bases"]:
            print(f"  - {base_id}")
    
    if changes["added_users"]:
        print(f"\n👤 Users gained access ({len(changes['added_users'])}):")
        for u in changes["added_users"]:
            print(f"  + {u['email']} → {u['base_name']} ({u['permission']})")
    
    if changes["removed_users"]:
        print(f"\n👤 Users lost access ({len(changes['removed_users'])}):")
        for u in changes["removed_users"]:
            print(f"  - {u['email']} ✗ {u['base_name']}")
    
    if changes["permission_changes"]:
        print(f"\n🔑 Permission changes ({len(changes['permission_changes'])}):")
        for u in changes["permission_changes"]:
            print(f"  ~ {u['email']} @ {u['base_name']}: {u['old_permission']} → {u['new_permission']}")
    
    total = (len(changes["added_users"]) + len(changes["removed_users"]) + 
             len(changes["permission_changes"]) + len(changes["new_bases"]) +
             len(changes["removed_bases"]))
    
    if total == 0:
        print("\n✓ No changes detected")
    
    print("")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Airtable base user access data")
    parser.add_argument("--login", action="store_true", help="Login and save auth state")
    parser.add_argument("--bases", nargs="+", help="Specific base IDs to scrape")
    parser.add_argument("--workspace", nargs="+", help="Filter to specific workspace(s) by ID or name")
    parser.add_argument("--from-api", action="store_true", help="Fetch base list from API")
    parser.add_argument("--save-config", action="store_true", help="Save/update workspace config from results")
    parser.add_argument("--show-config", action="store_true", help="Show current config and exit")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between bases (seconds)")
    parser.add_argument("--no-compare", action="store_true", help="Skip comparison with previous run")
    parser.add_argument("--debug", action="store_true", help="Save debug info (HTML, globals, network) to diagnose capture issues")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum retries for transient errors (default: 3)")
    parser.add_argument("--context-recycle", type=int, default=15, help="Recycle browser context every N requests (default: 15)")
    parser.add_argument("--max-delay", type=float, default=10.0, help="Maximum adaptive delay after errors in seconds (default: 10)")
    parser.add_argument("--export-csv-from-json", type=str, nargs="?", const="default", metavar="JSON_FILE",
                        help="Export CSV files from existing JSON (default: output/airtable_users_export.json)")

    args = parser.parse_args()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Load config
    config = load_config()
    
    # Show config and exit
    if args.show_config:
        print_config_summary(config)
        if config.get("workspaces"):
            print("\nDetailed config:")
            print(json.dumps(config, indent=2))
        return

    # Export CSVs from existing JSON and exit
    if args.export_csv_from_json:
        json_path = OUTPUT_FILE if args.export_csv_from_json == "default" else Path(args.export_csv_from_json)
        if not json_path.exists():
            print(f"Error: JSON file not found: {json_path}")
            return
        print(f"Loading reports from {json_path}...")
        reports = load_reports_from_json(json_path)
        print(f"Loaded {len(reports)} base reports")
        export_aggregated_csvs(reports)
        return

    async with AirtableScraper(
        headless=args.headless,
        debug=args.debug,
        context_recycle_interval=args.context_recycle,
        max_retries=args.max_retries,
    ) as scraper:
        if args.login:
            # Force non-headless for login
            scraper.headless = False
            scraper.browser = await scraper.playwright.chromium.launch(headless=False)
            await scraper.login_and_save_auth()
            return
        
        # Get base IDs
        if args.bases:
            base_ids = args.bases
        elif args.from_api:
            print("Fetching base list from API...")
            base_ids = await fetch_base_ids_from_api()
            print(f"Found {len(base_ids)} bases")
        elif args.workspace:
            # Filter to specific workspaces
            base_ids = get_workspace_base_ids(config, args.workspace)
            if not base_ids:
                print(f"No bases found for workspace(s): {args.workspace}")
                print_config_summary(config)
                return
            print(f"Filtering to {len(base_ids)} bases in workspace(s): {args.workspace}")
        elif config.get("workspaces"):
            base_ids = get_all_base_ids(config)
            if not base_ids:
                print("Config exists but no bases configured.")
                print_config_summary(config)
                return
            print(f"Using {len(base_ids)} bases from config")
            print_config_summary(config)
        else:
            print("No bases specified. Options:")
            print("  --bases BASE_ID...     Provide base IDs directly")
            print("  --from-api             Fetch from API (needs AIRTABLE_API_KEY)")
            print("  --workspace NAME/ID    Filter to specific workspace from config")
            print("  --show-config          Show current configuration")
            print("\nFirst run? Try:")
            print("  python airtable_user_scraper.py --from-api --save-config")
            return
        
        # Back up previous output
        previous_output = None
        if OUTPUT_FILE.exists() and not args.no_compare:
            backup_path = OUTPUT_FILE.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            import shutil
            shutil.copy(OUTPUT_FILE, backup_path)
            previous_output = backup_path
            print(f"Previous output backed up to {backup_path}")
        
        # Scrape
        reports = await scraper.scrape_multiple_bases(
            base_ids,
            delay_seconds=args.delay,
            max_delay_seconds=args.max_delay,
        )
        
        # Update config with workspace info from results
        if args.save_config:
            config = update_config_from_reports(config, reports)
            save_config(config)
            print_config_summary(config)
        
        # Compare with previous run
        if previous_output and not args.no_compare:
            changes = compare_reports(previous_output, reports)
            print_changes(changes)
        
        # Print workspace summary
        print_workspace_summary(reports)
        
        # Save JSON output
        output = {
            "scrape_time": datetime.now().isoformat(),
            "total_bases": len(reports),
            "successful": sum(1 for r in reports if not r.error),
            "failed": sum(1 for r in reports if r.error),
            "workspace_summary": generate_workspace_summary(reports),
            "bases": [r.to_dict() for r in reports]
        }
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        
        print(f"\nResults saved to {OUTPUT_FILE}")

        # Aggregated CSV exports (always generated)
        export_aggregated_csvs(reports)

        # Summary
        print(f"\nSummary:")
        print(f"  Scraped: {len(reports)} bases")
        print(f"  Successful: {output['successful']}")
        print(f"  Failed: {output['failed']}")
        
        # Unique users across all bases
        all_users = set()
        for r in reports:
            for u in r.users:
                all_users.add(u.email)
        print(f"  Unique users (total): {len(all_users)}")


if __name__ == "__main__":
    asyncio.run(main())