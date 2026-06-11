---
name: airtable-schema
description: "Export and inspect an Airtable base schema (tables, fields, views) using the airtable-export-schema utility. Use when the user wants to export a base schema, or when you need schema context before writing Airtable scripts."
---

# Airtable Schema Export Skill

## Purpose

This skill covers running `airtable-export-schema` to dump an Airtable base's full schema — tables, fields (with types and descriptions), and views — to JSON and/or Markdown.

## Direct Airtable Access via MCP

If the user wants Claude to **directly read or modify Airtable data**, use an Airtable MCP server instead:

```
/plugin install airtable@claude-plugins-official
```

The official plugin bundles Airtable's hosted MCP server (OAuth or PAT, nothing to run locally) and is the only one that can read **Interface pages** and **create whole bases**.

The community [`airtable-mcp-server`](https://github.com/domdomegg/airtable-mcp-server) by domdomegg is a self-hosted alternative (run via `npx` or its HTTP transport, PAT auth only) and is the one that can **delete records** and work with **record comments**. Its HTTP transport has no built-in auth, so only run it behind a reverse proxy or in a secured environment.

Both cover read/search/create/update of records and create/update of tables and fields.

This skill is for exporting schema metadata to a local file.

## Prerequisites

Install dependencies (first time only):

```bash
uv run --script bin/airtable-export-schema --help   # installs deps automatically via uv
# or manually: pip install requests
```

## Personal Access Token (PAT)

Create a PAT at [airtable.com/create/tokens](https://airtable.com/create/tokens).

Required scopes:
| Scope | Why |
|-------|-----|
| `schema.bases:read` | Read table/field/view schema |
| `base.bases:list` | Look up the base name from its ID |

The token must have access to the target base(s).

## Running the Exporter

```bash
# Using CLI flags
airtable-export-schema --token YOUR_PAT --base appXXXXXXXXXX

# Using environment variables (preferred for repeated use)
export AIRTABLE_TOKEN=patXXXXXXXXXX
export AIRTABLE_BASE_ID=appXXXXXXXXXX
airtable-export-schema

# Choose output format (default: both)
airtable-export-schema --token YOUR_PAT --base appXXXXXXXXXX --format json
```

## Credentials

Credentials are resolved in order: **CLI flags → environment variables → `.env` file** (current working directory, then the script's own directory).

> **Agents: never read `.env`** (no `cat`, `head`, `grep`, or the Read tool) — it contains secret values and access is typically deny-listed. Don't pre-check that credentials exist either. Just run the command: it loads `.env` automatically and exits with a clear error naming the missing variable if credentials aren't found. React to that error — the message suggests `fnox exec -- <command>` only when fnox is installed; retry with that if a `fnox.toml` is in scope, otherwise relay the error to the user.

### Using a .env File

Place a `.env` file in the directory where you run the command. The script loads it automatically.

```dotenv
# .env
AIRTABLE_TOKEN=patXXXXXXXXXX
AIRTABLE_BASE_ID=appXXXXXXXXXX
```

Then just run:

```bash
airtable-export-schema
```

**Per-folder credentials:** Because the script looks for `.env` in the *current working directory* first, you can keep a separate `.env` per project folder, each pointing at a different base or token.

### Using fnox (optional)

If the project manages secrets with [fnox](https://github.com/jdx/fnox) (a `fnox.toml` in the current directory or a parent), wrap the command so fnox resolves the secrets at run time:

```bash
fnox exec -- airtable-export-schema
```

Note: fnox's `fnox activate` cd-hook only fires in interactive shells — in non-interactive (agent) shells the `fnox exec` wrapper is required.

Output files are written to the current directory, named:
```
{base_id}_{base_name}_{timestamp}_schema.json
{base_id}_{base_name}_{timestamp}_schema.md
```
The `{timestamp}` is `YYYY-MM-DD_HH-MM-SS` (down to the second). If a file with the same name already exists, a `_1`, `_2`, … counter is appended, so an export never overwrites a previous one.

## Output Format

**JSON** — machine-readable, suitable for feeding to other scripts or tools:
```json
{
  "base": { "id": "appXXX", "name": "My Base" },
  "summary": {
    "tableCount": 1,
    "fieldCount": 2,
    "viewCount": 1,
    "tables": [
      { "id": "tblXXX", "name": "Tasks", "primaryFieldName": "Name", "fieldCount": 2, "viewCount": 1 }
    ]
  },
  "tables": [
    {
      "id": "tblXXX",
      "name": "Tasks",
      "fields": [
        { "id": "fldXXX", "name": "Name", "type": "singleLineText", "description": "" },
        { "id": "fldYYY", "name": "Status", "type": "singleSelect", "options": { "choices": [...] } }
      ],
      "views": [
        { "id": "viwXXX", "name": "Grid view", "type": "grid" }
      ]
    }
  ]
}
```

The `summary` object gives per-table stats (field count, view count, and resolved primary field name) plus base-wide totals — all derived from the schema, so no extra API calls or token scopes are needed. The raw `tables` array is unchanged, so downstream tools (diff, standards check) are unaffected.

**Markdown** — human-readable summary of the schema. The header shows base-wide totals (`Tables · Fields · Views`), and each table lists its primary field plus field/view counts before the fields table. The fields table has columns `# | Field Name | Field ID | Type | Options | Description`. The **Options** column summarises each field's configuration (number/currency precision, date/time format, select choices, rating max, linked-table ID with reversed/single flags, rollup/lookup/count source fields and result type, etc.). Nothing is truncated — descriptions and choice lists are shown in full.

## Workflow: Schema Before Scripting

When writing Airtable scripts, always export the schema first so you have accurate table, field, and view IDs. Feed the JSON output as context when using the `airtable-scripting` skill.

1. Export schema: `airtable-export-schema --token ... --base ...`
2. Read the output JSON to find exact IDs for tables, fields, and views
3. Use those IDs (never names) in scripts — see the `airtable-scripting` skill
