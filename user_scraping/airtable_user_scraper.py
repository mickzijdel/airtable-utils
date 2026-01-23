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
AUTH_STATE_FILE = Path("airtable_auth_state.json")
OUTPUT_FILE = Path("airtable_users_export.json")
CONFIG_FILE = Path("airtable_scraper_config.json")
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


class AirtableScraper:
    """
    Scrapes user access data from Airtable bases.
    
    The scraper works by intercepting the window.resolveLiveappDataPromise()
    call that Airtable makes when loading a base. This function receives a
    large JSON payload containing:
    - rawUsers: all users with access to workspace/base
    - collaboratorsByWorkspaceId: permission mappings at workspace level
    - collaboratorsByApplicationId: permission mappings at base level
    - rawWorkspaces: workspace metadata
    - rawApplications: base metadata
    """
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.captured_data: dict = {}
    
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
    
    async def scrape_base(self, base_id: str) -> BaseAccessReport:
        """
        Scrapes user access data from a single base.
        
        Args:
            base_id: Airtable base ID (e.g., 'appXXXXXXXXXXXXXX')
        
        Returns:
            BaseAccessReport with all users who have access
        """
        if not self.context:
            await self.load_auth()
        
        page = await self.context.new_page()
        self.captured_data = {}
        
        # Inject script to intercept the initialization data
        await page.add_init_script("""
            window.__airtableInitData = null;
            const originalResolve = window.resolveLiveappDataPromise;
            window.resolveLiveappDataPromise = function(data) {
                window.__airtableInitData = data;
                if (originalResolve) {
                    return originalResolve(data);
                }
            };
        """)
        
        try:
            url = f"https://airtable.com/{base_id}"
            print(f"  Loading {url}...")
            
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait for data to be captured (with timeout)
            for _ in range(50):  # 5 seconds max
                self.captured_data = await page.evaluate(
                    "() => window.__airtableInitData"
                )
                if self.captured_data:
                    break
                await asyncio.sleep(0.1)
            
            if not self.captured_data:
                # Fallback: try to extract from page source
                self.captured_data = await self._extract_from_source(page)
            
            if not self.captured_data:
                return BaseAccessReport(
                    base_id=base_id,
                    base_name="Unknown",
                    workspace_id="Unknown",
                    workspace_name="Unknown",
                    error="Failed to capture initialization data"
                )
            
            return self._parse_access_data(base_id, self.captured_data)
            
        except Exception as e:
            return BaseAccessReport(
                base_id=base_id,
                base_name="Unknown",
                workspace_id="Unknown",
                workspace_name="Unknown",
                error=str(e)
            )
        finally:
            await page.close()
    
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
        delay_seconds: float = 1.0
    ) -> list[BaseAccessReport]:
        """
        Scrapes multiple bases with a delay between requests.
        
        Args:
            base_ids: List of Airtable base IDs
            delay_seconds: Delay between scraping each base (be nice to Airtable)
        
        Returns:
            List of BaseAccessReport objects
        """
        reports = []
        total = len(base_ids)
        
        for i, base_id in enumerate(base_ids, 1):
            print(f"[{i}/{total}] Scraping base {base_id}...")
            report = await self.scrape_base(base_id)
            reports.append(report)
            
            if report.error:
                print(f"  Error: {report.error}")
            else:
                print(f"  Found {len(report.users)} users in '{report.base_name}'")
            
            if i < total:
                await asyncio.sleep(delay_seconds)
        
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


def export_to_csv(reports: list[BaseAccessReport], filename: str = "airtable_users.csv"):
    """Exports reports to a CSV file for easy viewing."""
    import csv
    
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Base ID", "Base Name", "Workspace ID", "Workspace", "User ID", 
            "Email", "Name", "Permission Level"
        ])
        
        for report in reports:
            if report.error:
                writer.writerow([
                    report.base_id, f"ERROR: {report.error}", "", "", "", "", "", ""
                ])
            else:
                for user in report.users:
                    writer.writerow([
                        report.base_id,
                        report.base_name,
                        report.workspace_id,
                        report.workspace_name,
                        user.id,
                        user.email,
                        user.full_name,
                        user.permission_level,
                    ])
    
    print(f"Exported to {filename}")


def export_per_workspace(reports: list[BaseAccessReport], output_dir: str = "."):
    """
    Export separate CSV files per workspace.
    
    Creates files like:
      - airtable_users_My_Organisation.csv
      - airtable_users_Research.csv
    """
    import csv
    from pathlib import Path
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Group reports by workspace
    by_workspace: dict[str, list[BaseAccessReport]] = {}
    for report in reports:
        ws_key = report.workspace_id or "unknown"
        if ws_key not in by_workspace:
            by_workspace[ws_key] = []
        by_workspace[ws_key].append(report)
    
    files_created = []
    
    for ws_id, ws_reports in by_workspace.items():
        # Get workspace name from first report
        ws_name = ws_reports[0].workspace_name or "Unknown"
        
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in ws_name)
        safe_name = safe_name.replace(" ", "_")
        
        filename = output_path / f"airtable_users_{safe_name}.csv"
        
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Base ID", "Base Name", "User ID", "Email", "Name", "Permission Level"
            ])
            
            for report in ws_reports:
                if report.error:
                    writer.writerow([
                        report.base_id, f"ERROR: {report.error}", "", "", "", ""
                    ])
                else:
                    for user in report.users:
                        writer.writerow([
                            report.base_id,
                            report.base_name,
                            user.id,
                            user.email,
                            user.full_name,
                            user.permission_level,
                        ])
        
        files_created.append((filename, ws_name, len(ws_reports)))
    
    print(f"\nExported {len(files_created)} workspace files:")
    for filepath, ws_name, base_count in files_created:
        print(f"  {filepath} ({ws_name}, {base_count} bases)")
    
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
        
        ws_id = report.workspace_id
        if ws_id == "Unknown" or not ws_id:
            continue
        
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
    parser.add_argument("--csv", type=str, help="Export to single CSV file")
    parser.add_argument("--csv-per-workspace", type=str, metavar="DIR", help="Export separate CSV per workspace to directory")
    parser.add_argument("--no-compare", action="store_true", help="Skip comparison with previous run")
    
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Show config and exit
    if args.show_config:
        print_config_summary(config)
        if config.get("workspaces"):
            print("\nDetailed config:")
            print(json.dumps(config, indent=2))
        return
    
    async with AirtableScraper(headless=args.headless) as scraper:
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
        reports = await scraper.scrape_multiple_bases(base_ids, delay_seconds=args.delay)
        
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
        
        # CSV exports
        if args.csv:
            export_to_csv(reports, args.csv)
        
        if args.csv_per_workspace:
            export_per_workspace(reports, args.csv_per_workspace)
        
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