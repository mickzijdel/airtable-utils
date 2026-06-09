import json
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
from conftest import load_bin_script

schema_diff = load_bin_script("airtable-diff-schema")

SCHEMA_A = {
    "tables": [
        {
            "id": "tblAAA",
            "name": "Applicant",
            "description": "",
            "primaryFieldId": "fldAAA1",
            "fields": [
                {"id": "fldAAA1", "name": "Name", "type": "singleLineText"},
                {"id": "fldAAA2", "name": "Email", "type": "email"},
            ],
            "views": [
                {"id": "viwAAA1", "name": "All", "type": "grid"},
            ],
        }
    ]
}

SCHEMA_B = {
    "tables": [
        {
            "id": "tblAAA",
            "name": "Applicant",
            "description": "",
            "primaryFieldId": "fldAAA1",
            "fields": [
                {
                    "id": "fldAAA1",
                    "name": "Full name",
                    "type": "singleLineText",
                },  # renamed
                {"id": "fldAAA2", "name": "Email", "type": "email"},
                {"id": "fldAAA3", "name": "Phone", "type": "phoneNumber"},  # added
            ],
            "views": [
                {"id": "viwAAA1", "name": "All", "type": "grid"},
            ],
        },
        {
            "id": "tblBBB",
            "name": "Application",
            "description": "",
            "primaryFieldId": "fldBBB1",
            "fields": [{"id": "fldBBB1", "name": "ID", "type": "autoNumber"}],
            "views": [],
        },
    ]
}


def test_detects_added_table():
    diff = schema_diff.diff_schemas(SCHEMA_A, SCHEMA_B)
    assert len(diff.added_tables) == 1
    assert diff.added_tables[0]["name"] == "Application"


def test_detects_renamed_field():
    diff = schema_diff.diff_schemas(SCHEMA_A, SCHEMA_B)
    assert len(diff.changed_tables) == 1
    td = diff.changed_tables[0]
    assert ("fldAAA1", "Name", "Full name") in td.renamed_fields


def test_detects_added_field():
    diff = schema_diff.diff_schemas(SCHEMA_A, SCHEMA_B)
    td = diff.changed_tables[0]
    assert any(f["name"] == "Phone" for f in td.added_fields)


def test_no_changes_returns_empty_diff():
    diff = schema_diff.diff_schemas(SCHEMA_A, SCHEMA_A)
    assert not diff.has_changes()


def test_format_contains_table_name():
    diff = schema_diff.diff_schemas(SCHEMA_A, SCHEMA_B)
    md = schema_diff.format_diff_as_markdown(diff)
    assert "Application" in md
    assert "added" in md.lower()


def test_detects_type_change():
    schema_before = {
        "tables": [
            {
                "id": "tblX",
                "name": "Thing",
                "description": "",
                "primaryFieldId": "fldX1",
                "fields": [{"id": "fldX1", "name": "Score", "type": "singleLineText"}],
                "views": [],
            }
        ]
    }
    schema_after = {
        "tables": [
            {
                "id": "tblX",
                "name": "Thing",
                "description": "",
                "primaryFieldId": "fldX1",
                "fields": [{"id": "fldX1", "name": "Score", "type": "number"}],
                "views": [],
            }
        ]
    }
    diff = schema_diff.diff_schemas(schema_before, schema_after)
    assert len(diff.changed_tables) == 1
    td = diff.changed_tables[0]
    assert len(td.changed_fields) == 1
    assert td.changed_fields[0].field_name == "Score"
    assert td.changed_fields[0].old_type == "singleLineText"
    assert td.changed_fields[0].new_type == "number"


def test_cli_prints_diff(tmp_path):
    old_file = tmp_path / "old.json"
    new_file = tmp_path / "new.json"
    old_file.write_text(json.dumps(SCHEMA_A))
    new_file.write_text(json.dumps(SCHEMA_B))
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent.parent / "bin" / "airtable-diff-schema"),
            str(old_file),
            str(new_file),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Application" in result.stdout
