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

The community [`airtable-mcp-server`](https://github.com/domdomegg/airtable-mcp-server) by domdomegg is an alternative (run via `npx` or Docker).

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

## Using a .env File (Recommended)

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

**Markdown** — human-readable summary of the schema. Each table renders a fields table with columns `# | Field Name | Field ID | Type | Options | Description`. The **Options** column summarises each field's configuration (number/currency precision, date/time format, select choices, rating max, linked-table ID with reversed/single flags, rollup/lookup/count source fields and result type, etc.). Nothing is truncated — descriptions and choice lists are shown in full.

## Workflow: Schema Before Scripting

When writing Airtable scripts, always export the schema first so you have accurate table, field, and view IDs. Feed the JSON output as context when using the `airtable-scripting` skill.

1. Export schema: `airtable-export-schema --token ... --base ...`
2. Read the output JSON to find exact IDs for tables, fields, and views
3. Use those IDs (never names) in scripts — see the `airtable-scripting` skill
