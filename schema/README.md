# Airtable Schema Exporter

Exports the complete schema of an Airtable base to JSON and/or Markdown, including tables, fields (with types and descriptions), and views.

## Requirements

```bash
pip install requests
```

## Usage

```bash
# Using CLI flags
python airtable_schema_export.py --token YOUR_TOKEN --base BASE_ID

# Using environment variables
AIRTABLE_TOKEN=YOUR_TOKEN AIRTABLE_BASE_ID=appXXXXXXXX python airtable_schema_export.py

# Using a .env file (recommended — loaded automatically from cwd or script dir)
# .env:
#   AIRTABLE_TOKEN=patXXXXXXXXXX
#   AIRTABLE_BASE_ID=appXXXXXXXX
python airtable_schema_export.py

# Options
python airtable_schema_export.py \
  --token YOUR_TOKEN \
  --base BASE_ID \
  --format json        # json | markdown | both (default: both)
```

**Per-folder credentials:** the script loads `.env` from the current working directory first, then from the script's own directory. Place a `.env` in each project folder to keep credentials separate per base.

Output files are named `{base_id}_{base_name}_{timestamp}_schema.json/.md` and written to the current directory.

## Personal Access Token (PAT)

Create a PAT at [airtable.com/create/tokens](https://airtable.com/create/tokens).

### Required scopes

| Scope | Why |
|-------|-----|
| `schema.bases:read` | Read table/field/view schema for the base |
| `base.bases:list` | Look up the base name from its ID |

### Required access

The token must have access to the base(s) you want to export. Add them under **Base access** when creating the token, or grant access to all bases you own.
