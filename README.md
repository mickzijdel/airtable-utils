# airtable-utils

A collection of useful tools and guidance for working with Airtable. Can be used in two ways:

- **As a Claude Code plugin** — install once and skills + CLI tools are automatically available to Claude
- **Standalone** — run the `bin/` scripts directly from the command line (requires [`uv`](https://docs.astral.sh/uv/)), or copy the `airtable-scripting` skill into any Claude (Code) session manually

## Skills

### `airtable-scripting`
Comprehensive guidance for writing Airtable scripts both as Scripting Extensions (manual) and Automation Scripts (triggered). Covers the Scripting API, Web API integration, all field types, batching, error handling, and common patterns.

Use this skill when writing scripts for the user to paste into Airtable.

> **Standalone use:** You can use this skill without installing the plugin. Copy [`skills/airtable-scripting.md`](skills/airtable-scripting.md) and load it manually in any Claude Code session.

> For Claude to **directly read or write Airtable data**, use the official [`airtable@claude-plugins-official`](https://www.airtable.com) plugin instead, which bundles the official MCP server.

### `airtable-schema`
Runs `airtable-export-schema` to dump a base's full schema (tables, fields, views) to JSON and Markdown. Use this before writing scripts so you have accurate IDs.

### `airtable-schema-diff`
Runs `airtable-diff-schema` to compare two schema JSON exports and produce a Markdown diff showing tables/fields/views that were added, removed, renamed, or had their type changed.

### `airtable-standards-check`
Runs `airtable-check-standards` to validate a schema JSON file against the [BlueDot Impact Airtable Standards](https://github.com/bluedotimpact/airtable-standards). Outputs a Markdown report grouped by table, listing errors and warnings. No API token or network access needed.

### `airtable-user-scraping`
Runs `airtable-scrape-users` to scrape collaborator access data from Airtable bases, grouped by workspace. Outputs per-workspace CSVs showing who has access to what.

> ⚠️ The user scraper violates Airtable's [Acceptable Use Policy](https://www.airtable.com/company/aup). Use at your own risk.

## Utilities

Scripts live in `bin/` and work both as standalone CLI tools and as plugin-managed commands. They use [PEP 723 inline script metadata](https://peps.python.org/pep-0723/) so `uv` handles dependencies automatically — no virtualenv setup needed.

> **Standalone use:** Clone the repo, make sure [`uv`](https://docs.astral.sh/uv/) is on your PATH, and run `bin/airtable-export-schema` directly (or add `bin/` to your PATH).

### `airtable-export-schema`

Exports a base's schema via the Airtable API. Writes `{base_id}_{name}_{timestamp}_schema.json/.md` to the current directory.

**Dependencies:** `requests` (installed automatically by uv)

```bash
airtable-export-schema --token YOUR_PAT --base appXXXXXXXXXX
# or use a .env with AIRTABLE_TOKEN and AIRTABLE_BASE_ID
airtable-export-schema
```

### `airtable-diff-schema`

Compares two schema JSON files produced by `airtable-export-schema`. Outputs a Markdown diff of tables, fields, and views — detecting renames by entity ID.

**Dependencies:** none (stdlib only)

```bash
airtable-diff-schema old_schema.json new_schema.json
airtable-diff-schema old.json new.json --output diff.md
```

### `airtable-check-standards`

Validates a schema JSON file against the [BlueDot Impact Airtable Standards](https://github.com/bluedotimpact/airtable-standards). Outputs a Markdown report grouped by table. Exits with code 1 if any errors are found (CI-friendly).

**Dependencies:** none (stdlib only)

```bash
airtable-check-standards schema.json
airtable-check-standards schema.json --errors-only        # suppress warnings
airtable-check-standards schema.json --output report.md   # write to file
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

### As a Claude Code plugin

The repo serves as its own marketplace. Add it once, then install the plugin:

```
/plugin marketplace add mickzijdel/airtable-utils
/plugin install airtable-utils@airtable-utils
```

> **SSH error?** If installation fails with `git@github.com: Permission denied (publickey)`, Claude Code is trying to clone via SSH. Either [add an SSH key to your GitHub account](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account), or run this once to redirect GitHub clones to HTTPS instead:
> ```bash
> git config --global url."https://github.com/".insteadOf "git@github.com:"
> ```
> Then retry the install.

For local testing without installing:

```bash
claude --plugin-dir /path/to/airtable-utils
```

Skills are namespaced after install: `/airtable-utils:airtable-scripting`, `/airtable-utils:airtable-schema`, `/airtable-utils:airtable-schema-diff`, `/airtable-utils:airtable-standards-check`, `/airtable-utils:airtable-user-scraping`.

### Standalone (no Claude Code plugin needed)

```bash
git clone https://github.com/mickzijdel/airtable-utils
cd airtable-utils
# Run any script directly — uv handles dependencies automatically
bin/airtable-export-schema --help
```
