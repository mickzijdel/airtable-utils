---
name: airtable-schema-diff
description: "Compare two Airtable schema exports to see what changed between them. Use when the user wants to diff two schema JSON files, detect table/field/view additions, removals, renames, or type changes."
---

# Airtable Schema Diff Skill

## Purpose

This skill covers running `airtable-diff-schema` to compare two schema JSON files produced by `airtable-export-schema`. It reports what changed between them: tables added or removed, fields added/removed/renamed/type-changed, and views added/removed/renamed.

Comparisons are done by entity ID, so renames are detected correctly rather than showing as a remove + add.

## Prerequisites

No external dependencies — the script uses the Python standard library only.

## Running the Diff

```bash
# Print diff to stdout
airtable-diff-schema old_schema.json new_schema.json

# Write diff report to a file
airtable-diff-schema old_schema.json new_schema.json --output diff.md
```

Both arguments are schema JSON files as produced by `airtable-export-schema`.

## Output Format

The output is a Markdown report structured as follows:

```
# Schema Diff: <base name>

## Tables

### Added
- TableName

### Removed
- TableName

## Fields in <TableName>

### Added
- FieldName (type)

### Removed
- FieldName

### Renamed
- OldName → NewName

### Type changed
- FieldName: oldType → newType

## Views in <TableName>

### Added
- ViewName

### Removed
- ViewName

### Renamed
- OldName → NewName
```

Tables and sections with no changes are omitted from the report. If there are no differences at all, the report says so explicitly.

## Workflow

1. Export the old schema (or use a previously saved one): `airtable-export-schema`
2. Make changes in Airtable
3. Export the new schema: `airtable-export-schema`
4. Diff them: `airtable-diff-schema old_schema.json new_schema.json`
