---
name: airtable-user-scraping
description: "Scrape user/collaborator access data from Airtable bases using the airtable-scrape-users utility. Use when the user wants to audit who has access to which Airtable bases and at what permission level."
---

# Airtable User Scraper Skill

## Purpose

This skill covers running `airtable-scrape-users` to extract user/collaborator data from Airtable bases grouped by workspace. Airtable's API does not expose collaborator data on the Team plan; this tool scrapes it from the web UI instead.

## ⚠️ Important: Acceptable Use Policy

**This tool violates Airtable's [Acceptable Use Policy](https://www.airtable.com/company/aup).** Always warn the user and obtain explicit acknowledgment before proceeding.

## Prerequisites

Install Playwright's browser (first time only):

```bash
playwright install chromium
# Dependencies are handled automatically by uv on first run
```

## Workflow

### Step 1: Login (once per ~30 days)

Opens a browser for manual authentication. Auth cookies are saved to `output/airtable_auth_state.json`.

```bash
airtable-scrape-users --login
```

Re-run `--login` if scraping starts failing (cookies expire after ~30 days).

### Step 2: Discover bases and save workspace config (once, or when bases change)

Fetches all accessible bases from the Airtable API and saves workspace groupings to `output/airtable_scraper_config.json`.

```bash
export AIRTABLE_API_KEY=patXXXXXXXXXX
airtable-scrape-users --from-api --save-config
```

**Tip:** Place a `.env` file in the directory you run the command from. It is loaded automatically.

```dotenv
# .env
AIRTABLE_API_KEY=patXXXXXXXXXX
```

### Step 3: Scrape user data

Uses the saved config. Shows changes compared to the previous run.

```bash
airtable-scrape-users
```

## Common Options

```bash
# Filter to specific workspace(s) by name or ID
airtable-scrape-users --workspace "Operations"
airtable-scrape-users --workspace "Operations" "Research"

# Scrape specific base IDs only
airtable-scrape-users --bases appXXXXXXXXXX appYYYYYYYYYY

# Export CSVs from the latest JSON without re-scraping
airtable-scrape-users --export-csv-from-json

# Export CSVs from a specific JSON file
airtable-scrape-users --export-csv-from-json output/airtable_users_export.20260123_114935.json

# Skip change comparison
airtable-scrape-users --no-compare

# Slow down requests (default: 1.0 second between bases)
airtable-scrape-users --delay 2

# Debug: show browser and save diagnostic HTML
airtable-scrape-users --no-headless --debug
```

## Output Files

All output is written to `output/` in the current working directory:

| File | Contents |
|------|---------|
| `airtable_auth_state.json` | Browser cookies — gitignored |
| `airtable_scraper_config.json` | Workspace/base mapping |
| `airtable_users_export.json` | Latest results |
| `airtable_users_export.YYYYMMDD_HHMMSS.json` | Backup of previous run |
| `{Workspace}_users.csv` | One row per user, columns = bases, values = permission level |
| `{Workspace}_bases.csv` | One row per base, columns = users, values = permission level |

## Permission Levels

- `owner` — Full admin
- `create` — Create/edit records
- `edit` — Edit records only
- `comment` — Comment only
- `read` — Read-only

Service accounts (AI, Automations, Table Sync) are automatically excluded.

## Console Output

Each run prints:
- Per-base progress and user counts
- Change detection: users added/removed, permission changes since last run
- Workspace summary with unique user counts

## JSON Structure

```json
{
  "scrape_time": "2026-01-23T...",
  "total_bases": 17,
  "workspace_summary": {
    "wspXXXXXXXXXXX": {
      "workspace_name": "Operations",
      "base_count": 12,
      "unique_user_count": 9,
      "users": [...]
    }
  },
  "bases": [...]
}
```
