# airtable-utils

A Claude Code plugin with skills and utilities for working with Airtable.

## Skills

### `airtable-scripting`
Comprehensive guidance for writing Airtable scripts — both Scripting Extensions (manual) and Automation Scripts (triggered). Covers the Scripting API, Web API integration, all field types, batching, error handling, and common patterns.

Use this skill when writing scripts for the user to paste into Airtable.

> For Claude to **directly read or write Airtable data**, use the official [`airtable@claude-plugins-official`](https://www.airtable.com) plugin instead, which bundles the official MCP server.

### `airtable-schema`
Runs `airtable-export-schema` to dump a base's full schema (tables, fields, views) to JSON and Markdown. Use this before writing scripts so you have accurate IDs.

### `airtable-user-scraping`
Runs `airtable-scrape-users` to scrape collaborator access data from Airtable bases, grouped by workspace. Outputs per-workspace CSVs showing who has access to what.

> ⚠️ The user scraper violates Airtable's [Acceptable Use Policy](https://www.airtable.com/company/aup). Use at your own risk.

## Utilities

Scripts live in `bin/` and are automatically on `PATH` when the plugin is enabled. They use [PEP 723 inline script metadata](https://peps.python.org/pep-0723/) so `uv` handles dependencies automatically.

### `airtable-export-schema`

Exports a base's schema via the Airtable API. Writes `{base_id}_{name}_{timestamp}_schema.json/.md` to the current directory.

**Dependencies:** `requests` (installed automatically by uv)

```bash
airtable-export-schema --token YOUR_PAT --base appXXXXXXXXXX
# or use a .env with AIRTABLE_TOKEN and AIRTABLE_BASE_ID
airtable-export-schema
```

### `airtable-scrape-users`

Scrapes user/collaborator data from the Airtable web UI (the API doesn't expose this on the Team plan). Writes output to `output/` in the current directory.

**Dependencies:** `playwright`, `aiohttp` (installed automatically by uv)  
**One-time browser install:** `playwright install chromium`

```bash
airtable-scrape-users --login                         # first-time auth
airtable-scrape-users --from-api --save-config        # discover bases
airtable-scrape-users                                  # scrape
```

## Credentials

Place a `.env` file in the directory you run the commands from:

```dotenv
AIRTABLE_TOKEN=patXXXXXXXXXX       # for airtable-export-schema
AIRTABLE_API_KEY=patXXXXXXXXXX     # for airtable-scrape-users
AIRTABLE_BASE_ID=appXXXXXXXX       # optional, for airtable-export-schema
```

## Installation

The repo serves as its own marketplace. Add it once, then install the plugin:

```
/plugin marketplace add mickzijdel/airtable_utils
/plugin install airtable-utils@airtable-utils
```

For local testing without installing:

```bash
claude --plugin-dir /path/to/airtable_utils
```

Skills are namespaced after install: `/airtable-utils:airtable-scripting`, `/airtable-utils:airtable-schema`, `/airtable-utils:airtable-user-scraping`.
