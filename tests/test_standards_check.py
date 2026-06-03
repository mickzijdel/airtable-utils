import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conftest import load_bin_script

standards = load_bin_script("airtable-check-standards")

CLEAN_SCHEMA = {
    "tables": [
        {
            "id": "tblAAA",
            "name": "Applicant",
            "description": "Description: Stores applicants\nLast reviewed on: 2025-01-01\nOwner: team@example.com",
            "primaryFieldId": "fldAAA1",
            "fields": [
                {"id": "fldAAA1", "name": "Name", "type": "singleLineText"},
                {"id": "fldAAA2", "name": "Is approved", "type": "checkbox"},
                {"id": "fldAAA3", "name": "Applied on", "type": "date"},
                {"id": "fldAAA4", "name": "Updated at", "type": "dateTime"},
            ],
            "views": [
                {"id": "viwAAA1", "name": "All", "type": "grid"},
            ],
        }
    ]
}

DIRTY_SCHEMA = {
    "tables": [
        {
            "id": "tblBBB",
            "name": "applicants",           # lowercase + plural
            "description": "",              # missing description keys
            "primaryFieldId": "fldBBB1",
            "fields": [
                {"id": "fldBBB1", "name": "applicants name", "type": "singleLineText"},  # lowercase + repeats table name
                {"id": "fldBBB2", "name": "approved", "type": "checkbox"},              # boolean not starting with "Is"
                {"id": "fldBBB3", "name": "application date", "type": "date"},          # date not ending in "on"
                {"id": "fldBBB4", "name": "last modified", "type": "dateTime"},         # datetime not ending in "at"
            ],
            "views": [
                {"id": "viwBBB1", "name": "Grid view", "type": "grid"},                # no "All" view
            ],
        }
    ]
}


def test_clean_schema_has_no_violations():
    violations = standards.check_schema(CLEAN_SCHEMA)
    assert violations == [], f"Expected no violations, got: {violations}"


def test_detects_table_name_not_sentence_case():
    violations = standards.check_schema(DIRTY_SCHEMA)
    assert any(v.rule == "table-sentence-case" for v in violations)


def test_detects_missing_all_view():
    violations = standards.check_schema(DIRTY_SCHEMA)
    assert any(v.rule == "table-missing-all-view" for v in violations)


def test_detects_boolean_field_not_starting_with_is():
    violations = standards.check_schema(DIRTY_SCHEMA)
    assert any(v.rule == "field-boolean-is-prefix" for v in violations)


def test_detects_date_field_not_ending_in_on():
    violations = standards.check_schema(DIRTY_SCHEMA)
    assert any(v.rule == "field-date-on-suffix" for v in violations)


def test_detects_datetime_field_not_ending_in_at():
    violations = standards.check_schema(DIRTY_SCHEMA)
    assert any(v.rule == "field-datetime-at-suffix" for v in violations)


def test_violation_has_expected_shape():
    violations = standards.check_schema(DIRTY_SCHEMA)
    v = violations[0]
    assert v.severity in ("error", "warning")
    assert v.entity_type in ("table", "field", "view")
    assert v.rule
    assert v.message


def test_cli_exits_nonzero_on_errors(tmp_path):
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(DIRTY_SCHEMA))
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "bin" / "airtable-check-standards"),
         str(schema_file)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "violation" in result.stdout.lower()


def test_cli_exits_zero_on_clean_schema(tmp_path):
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(CLEAN_SCHEMA))
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "bin" / "airtable-check-standards"),
         str(schema_file)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
