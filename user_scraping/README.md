# Airtable Base User Scraper

Scrapes user access data from Airtable bases, grouped by workspace.

NOTE THAT THIS GOES AGAINST THEIR [ACCEPTABLE USE POLICY](https://www.airtable.com/company/aup)! USE AT YOUR OWN RISK

## Problem
Airtable's API doesn't expose user/collaborator data on the Team plan. But the web UI contains this data in the page's initialization JavaScript (`window.resolveLiveappDataPromise({...})`).

## Setup

```bash
pip install playwright aiohttp --break-system-packages
playwright install chromium
```

## Quick Start

```bash
# 1. Login (opens browser for manual auth)
python airtable_user_scraper.py --login

# 2. Scrape all bases and save workspace config
export AIRTABLE_API_KEY=pat...
python airtable_user_scraper.py --from-api --save-config

# 3. Future runs (uses saved config, shows changes)
python airtable_user_scraper.py
```

## Workspace-Based Workflow

The config groups bases by workspace:

```json
{
  "workspaces": {
    "wspXXXXXXXXXXXXXX": {
      "name": "My Organisation",
      "base_ids": ["appXXXXXXXXXXXXXX", "appXXXXXXXXXX"]
    },
    "wspYYYYYYYYYYYYY": {
      "name": "Research",
      "base_ids": ["appAAAAAAAAAAAAA", "appBBBBBBBBBBBBB"]
    }
  }
}
```

**Filter by workspace:**
```bash
# By name (case-insensitive)
python airtable_user_scraper.py --workspace "My Organisation"

# By ID
python airtable_user_scraper.py --workspace wspXXXXXXXXXXXXXX

# Multiple workspaces
python airtable_user_scraper.py --workspace "Operations" "Research"
```

**Per-workspace aggregated CSVs (automatically generated):**

Every scrape automatically creates per-workspace CSV files in `output/`:
- `{Workspace}_users.csv` - One row per user, showing which bases they have each permission level for
- `{Workspace}_bases.csv` - One row per base, showing which users have each permission level

Example:
```
output/My_Organisation_users.csv
output/My_Organisation_bases.csv
output/Unknown_users.csv
output/Unknown_bases.csv
```

**Export CSVs from existing JSON (no re-scrape needed):**
```bash
python airtable_user_scraper.py --export-csv-from-json
# Or specify a different JSON file:
python airtable_user_scraper.py --export-csv-from-json output/airtable_users_export.20260122_143000.json
```

**Legacy per-workspace CSV exports (flat format):**
```bash
python airtable_user_scraper.py --csv-per-workspace ./reports/
# Creates:
#   ./reports/airtable_users_My_Organisation.csv
#   ./reports/airtable_users_Research.csv
```

## All Options

```
--login               Open browser for manual login
--bases ID...         Scrape specific base IDs
--workspace NAME/ID   Filter to specific workspace(s)
--from-api            Fetch all bases from Airtable API
--save-config         Save workspace config from results
--show-config         Show current config and exit
--delay N             Seconds between requests (default: 1.0)
--csv FILE            Export all results to single CSV
--csv-per-workspace   Export separate CSV per workspace (flat format)
--export-csv-from-json [FILE]  Export CSVs from existing JSON (default: latest export)
--no-compare          Skip comparison with previous run
--no-headless         Show browser (for debugging)
--debug               Save diagnostic info when capture fails
```

## Output

**Console output includes:**
- Per-base progress and user counts
- Change detection (users added/removed, permission changes)
- Workspace summary with unique user counts

Example:
```
============================================================
WORKSPACE SUMMARY
============================================================

📁 My Organisation (wspXXXXXXXXXXXXXX)
   Bases: 12
   Unique users: 9
   Permissions: create: 7, owner: 2

📁 Research (wspYYYYYYYYYYYYY)
   Bases: 5
   Unique users: 15
   Permissions: create: 10, owner: 3, read: 2
```

**JSON output (`airtable_users_export.json`):**
```json
{
  "scrape_time": "2026-01-23T...",
  "total_bases": 17,
  "workspace_summary": {
    "wspXXXXXXXXXXXXXX": {
      "workspace_name": "My Organisation",
      "base_count": 12,
      "unique_user_count": 9,
      "users": [...]
    }
  },
  "bases": [...]
}
```

## Files Generated

All output files are stored in the `output/` directory:

| File | Purpose |
|------|---------|
| `output/airtable_auth_state.json` | Browser cookies (add to .gitignore) |
| `output/airtable_scraper_config.json` | Workspace/base config |
| `output/airtable_users_export.json` | Latest results |
| `output/airtable_users_export.YYYYMMDD_HHMMSS.json` | Backup of previous run |
| `output/{Workspace}_users.csv` | Per-workspace user permissions (aggregated) |
| `output/{Workspace}_bases.csv` | Per-workspace base permissions (aggregated) |
| `output/debug/{base_id}.html` | Debug HTML (with --debug) |
| `output/debug/{base_id}_report.txt` | Debug report (with --debug) |

## Permission Levels

- `owner` - Full admin
- `create` - Create/edit records
- `edit` - Edit records only
- `comment` - Comment only
- `read` - Read-only

## Notes

- Service accounts (AI, Automations, Table Sync) are excluded
- Auth cookies last ~30 days; re-run `--login` if scraping fails
- Default 1-second delay between bases to avoid rate limiting
- The `--save-config` flag learns workspace structure from scrape results