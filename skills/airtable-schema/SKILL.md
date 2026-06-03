---
name: airtable-schema
description: "Export and inspect an Airtable base schema (tables, fields, views) using the airtable_schema_export.py utility. Use when the user wants to export a base schema, or when you need schema context before writing Airtable scripts."
---

# Airtable Schema Export Skill

## Purpose

This skill covers running the `schema/airtable_schema_export.py` utility to dump an Airtable base's full schema — tables, fields (with types and descriptions), and views — to JSON and/or Markdown.

## Direct Airtable Access via MCP

If the user wants Claude to **directly read or modify Airtable data**, use the official Airtable MCP plugin instead:

```
/plugin install airtable@claude-plugins-official
```

This skill is for exporting schema metadata to a local file.

## Prerequisites

```bash
pip install requests
```

The script lives at `schema/airtable_schema_export.py` relative to the repo root.

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
python schema/airtable_schema_export.py --token YOUR_PAT --base appXXXXXXXXXX

# Using environment variables (preferred for repeated use)
export AIRTABLE_TOKEN=patXXXXXXXXXX
export AIRTABLE_BASE_ID=appXXXXXXXXXX
python schema/airtable_schema_export.py

# Choose output format (default: both)
python schema/airtable_schema_export.py \
  --token YOUR_PAT \
  --base appXXXXXXXXXX \
  --format json        # json | markdown | both
```

Output files are written to the current directory, named:
```
{base_id}_{base_name}_{timestamp}_schema.json
{base_id}_{base_name}_{timestamp}_schema.md
```

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

**Markdown** — human-readable summary of the schema.

## Workflow: Schema Before Scripting

When writing Airtable scripts, always export the schema first so you have accurate table, field, and view IDs. Feed the JSON output as context when using the `airtable-scripting` skill.

1. Export schema: `python schema/airtable_schema_export.py --token ... --base ...`
2. Read the output JSON to find exact IDs for tables, fields, and views
3. Use those IDs (never names) in scripts — see the `airtable-scripting` skill
