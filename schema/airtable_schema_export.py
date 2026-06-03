"""
Airtable Base Schema Exporter

Downloads the complete schema of an Airtable base including:
- Tables (name, ID)
- Fields (name, type, description, options)
- Views (name, type)

Usage:
    python airtable_schema_export.py --token YOUR_TOKEN --base BASE_ID [--output schema.json]
    AIRTABLE_TOKEN=YOUR_TOKEN AIRTABLE_BASE_ID=BASE_ID python airtable_schema_export.py

Requirements:
    pip install requests
"""

import argparse
import json
import os
import requests
from datetime import datetime
from typing import Any


def get_base_info(token: str, base_id: str) -> str:
    """Fetch the base name for a given base ID."""
    url = "https://api.airtable.com/v0/meta/bases"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    bases = response.json().get("bases", [])
    for base in bases:
        if base.get("id") == base_id:
            return base.get("name", base_id)
    return base_id


def get_base_schema(token: str, base_id: str) -> dict[str, Any]:
    """
    Fetch the complete schema for an Airtable base.
    
    Args:
        token: Airtable Personal Access Token
        base_id: The base ID (starts with 'app')
    
    Returns:
        Dictionary containing the full base schema
    """
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    return response.json()


def format_schema_as_markdown(schema: dict[str, Any], base_id: str, base_name: str) -> str:
    """
    Convert the schema to a readable markdown format.

    Args:
        schema: The raw schema from Airtable API
        base_id: The base ID for reference
        base_name: The human-readable base name

    Returns:
        Markdown-formatted string
    """
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    lines = [f"# Airtable Base Schema: {base_name} (`{base_id}`) — {timestamp}\n"]
    lines.append(f"**Base:** {base_name}  ")
    lines.append(f"**App ID:** `{base_id}`  ")
    lines.append(f"**Exported:** {timestamp}\n")
    
    for table in schema.get("tables", []):
        table_name = table.get("name", "Unnamed Table")
        table_id = table.get("id", "")
        
        lines.append(f"\n## Table: {table_name}")
        lines.append(f"**ID:** `{table_id}`")
        
        # Description if present
        if table.get("description"):
            lines.append(f"\n**Description:** {table['description']}")
        
        # Fields
        lines.append("\n### Fields\n")
        lines.append("| # | Field Name | Field ID | Type | Description |")
        lines.append("|---|------------|----------|------|-------------|")

        for i, field in enumerate(table.get("fields", []), 1):
            field_name = field.get("name", "")
            field_id = field.get("id", "")
            field_type = field.get("type", "")
            field_desc = field.get("description", "").replace("\n", " ").replace("|", "\\|")

            # Add options info for select fields
            options = field.get("options", {})
            if field_type in ("singleSelect", "multipleSelects") and "choices" in options:
                choices = [c.get("name", "") for c in options["choices"][:5]]
                if len(options["choices"]) > 5:
                    choices.append(f"... +{len(options['choices']) - 5} more")
                field_desc += f" Choices: {', '.join(choices)}"
            elif field_type == "multipleRecordLinks":
                linked_table = options.get("linkedTableId", "")
                field_desc += f" → Links to `{linked_table}`"

            lines.append(f"| {i} | {field_name} | `{field_id}` | {field_type} | {field_desc[:100]}{'...' if len(field_desc) > 100 else ''} |")
        
        # Views
        views = table.get("views", [])
        if views:
            lines.append("\n### Views\n")
            lines.append("| View Name | Type |")
            lines.append("|-----------|------|")
            for view in views:
                view_name = view.get("name", "")
                view_type = view.get("type", "")
                lines.append(f"| {view_name} | {view_type} |")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Export Airtable base schema to JSON or Markdown"
    )
    parser.add_argument(
        "--token", "-t",
        default=os.environ.get("AIRTABLE_TOKEN"),
        help="Airtable Personal Access Token (or set AIRTABLE_TOKEN env var)"
    )
    parser.add_argument(
        "--base", "-b",
        default=os.environ.get("AIRTABLE_BASE_ID"),
        help="Base ID (starts with 'app') (or set AIRTABLE_BASE_ID env var)"
    )
    parser.add_argument(
        "--output", "-o",
        default="schema.json",
        help="Output filename (use .json or .md extension)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format"
    )
    
    args = parser.parse_args()

    if not args.token:
        parser.error("--token is required (or set AIRTABLE_TOKEN env var)")
    if not args.base:
        parser.error("--base is required (or set AIRTABLE_BASE_ID env var)")

    print(f"Fetching schema for base: {args.base}")
    base_name = get_base_info(args.token, args.base)
    print(f"Base name: {base_name}")
    schema = get_base_schema(args.token, args.base)

    # Count tables and fields
    num_tables = len(schema.get("tables", []))
    num_fields = sum(len(t.get("fields", [])) for t in schema.get("tables", []))
    num_views = sum(len(t.get("views", [])) for t in schema.get("tables", []))
    print(f"Found {num_tables} tables, {num_fields} fields, {num_views} views")

    # Build output filename stem from date, time, base name and app ID
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M")
    safe_base_name = base_name.replace(" ", "_").replace("/", "-")
    file_stem = f"{args.base}_{safe_base_name}_{timestamp}_schema"

    if args.format in ("json", "both"):
        json_file = f"{file_stem}.json"
        with open(json_file, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"JSON schema saved to: {json_file}")

    if args.format in ("markdown", "both"):
        md_file = f"{file_stem}.md"
        markdown = format_schema_as_markdown(schema, args.base, base_name)
        with open(md_file, "w") as f:
            f.write(markdown)
        print(f"Markdown schema saved to: {md_file}")


if __name__ == "__main__":
    main()