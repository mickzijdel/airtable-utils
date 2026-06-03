---
name: airtable-standards-check
description: "Check an Airtable schema JSON file against the BlueDot Impact Airtable Standards. Use when the user wants to validate their Airtable base structure, find naming convention violations, or produce a standards compliance report."
---

# Airtable Standards Check Skill

## Purpose

This skill covers running `airtable-check-standards` to validate a schema JSON file (produced by `airtable-export-schema`) against the [BlueDot Impact Airtable Standards](https://github.com/bluedotimpact/airtable-standards). It outputs a Markdown report grouped by table, listing errors and warnings for each rule violation.

## Prerequisites

No external dependencies — the script uses the Python standard library only. No API token or network access needed.

## Running the Checker

```bash
# Check a schema and print report to stdout
airtable-check-standards schema.json

# Suppress warnings, show errors only
airtable-check-standards schema.json --errors-only

# Write the report to a file
airtable-check-standards schema.json --output report.md

# Both flags combined
airtable-check-standards schema.json --errors-only --output report.md
```

The script exits with code `0` if no errors are found, or `1` if any errors are found — making it suitable for CI pipelines.

## Rules

The following rules are checked automatically:

| Rule | Severity | Check |
|------|----------|-------|
| `table-sentence-case` | error | Table name starts with uppercase |
| `table-singular` | warning | Table name isn't plural (heuristic) |
| `table-description-keys` | warning | Description has "Description:" and "Last reviewed on:" |
| `table-missing-all-view` | warning | Table has an "All" view |
| `field-sentence-case` | error | Field name (after `[prefix]` strip) starts with uppercase |
| `field-boolean-is-prefix` | warning | Checkbox fields start with "Is " |
| `field-date-on-suffix` | warning | Date fields end in " on" |
| `field-datetime-at-suffix` | warning | DateTime fields end in " at" |
| `field-repeats-table-name` | warning | Field name doesn't repeat table name words |

### Rules Requiring Manual Review

The following standards cannot be checked automatically and require human judgment:

- Whether table/field descriptions are meaningful (not just present)
- Whether tables or bases should be merged to reduce duplication
- Automation naming conventions

## Workflow

1. Export the schema: `airtable-export-schema --token ... --base ...`
2. Run the checker: `airtable-check-standards {base_id}_{name}_{timestamp}_schema.json`
3. Review the report and fix violations in Airtable
4. Re-export and re-check until the report is clean
