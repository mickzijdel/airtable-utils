import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conftest import load_bin_script

export_schema = load_bin_script("airtable-export-schema")
summarize = export_schema._summarize_field_options
render = export_schema.format_schema_as_markdown
build_output = export_schema.build_output
primary_field_name = export_schema._primary_field_name
build_summary = export_schema._build_summary


# ---------------------------------------------------------------------------
# build_output (JSON wrapper carrying base identity)
# ---------------------------------------------------------------------------

def test_build_output_adds_base_identity():
    schema = {"tables": [{"id": "tblA", "name": "Applicant"}]}
    out = build_output(schema, "appXXX", "My Base")
    assert out["base"] == {"id": "appXXX", "name": "My Base"}
    # tables preserved, base listed first
    assert out["tables"] == schema["tables"]
    assert list(out.keys())[0] == "base"


def test_build_output_does_not_mutate_input():
    schema = {"tables": []}
    build_output(schema, "appXXX", "My Base")
    assert "base" not in schema
    assert "summary" not in schema


def test_build_output_includes_summary():
    schema = {
        "tables": [
            {
                "id": "tblA",
                "name": "Applicant",
                "primaryFieldId": "fld2",
                "fields": [
                    {"id": "fld1", "name": "Score"},
                    {"id": "fld2", "name": "Name"},
                ],
                "views": [{"id": "viw1", "name": "All"}],
            }
        ]
    }
    out = build_output(schema, "appXXX", "My Base")
    # base stays first, tables preserved untouched
    assert list(out.keys())[0] == "base"
    assert out["tables"] == schema["tables"]
    # summary present and correct
    assert out["summary"]["tableCount"] == 1
    assert out["summary"]["fieldCount"] == 2
    assert out["summary"]["viewCount"] == 1
    assert out["summary"]["tables"][0] == {
        "id": "tblA",
        "name": "Applicant",
        "primaryFieldName": "Name",
        "fieldCount": 2,
        "viewCount": 1,
    }


# ---------------------------------------------------------------------------
# _primary_field_name
# ---------------------------------------------------------------------------

def test_primary_field_name_resolves_non_first_field():
    table = {
        "primaryFieldId": "fld3",
        "fields": [
            {"id": "fld1", "name": "First"},
            {"id": "fld2", "name": "Second"},
            {"id": "fld3", "name": "Third"},
        ],
    }
    assert primary_field_name(table) == "Third"


def test_primary_field_name_falls_back_to_first_field():
    table = {"fields": [{"id": "fld1", "name": "First"}, {"id": "fld2", "name": "Second"}]}
    assert primary_field_name(table) == "First"
    # unmatched id also falls back to first
    table_bad = {"primaryFieldId": "nope", "fields": table["fields"]}
    assert primary_field_name(table_bad) == "First"


def test_primary_field_name_empty_fields():
    assert primary_field_name({"fields": []}) == ""
    assert primary_field_name({}) == ""


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------

def test_build_summary_totals_and_per_table():
    schema = {
        "tables": [
            {
                "id": "tblA",
                "name": "Applicant",
                "primaryFieldId": "fld1",
                "fields": [{"id": "fld1", "name": "Name"}, {"id": "fld2", "name": "Age"}],
                "views": [{"id": "v1", "name": "Grid"}, {"id": "v2", "name": "Form"}],
            },
            {
                "id": "tblB",
                "name": "Cohort",
                "primaryFieldId": "fldX",
                "fields": [{"id": "fldX", "name": "Title"}],
                "views": [{"id": "v3", "name": "Grid"}],
            },
        ]
    }
    summary = build_summary(schema)
    assert summary["tableCount"] == 2
    assert summary["fieldCount"] == 3
    assert summary["viewCount"] == 3
    assert [t["name"] for t in summary["tables"]] == ["Applicant", "Cohort"]
    assert summary["tables"][0]["primaryFieldName"] == "Name"
    assert summary["tables"][1]["primaryFieldName"] == "Title"


# ---------------------------------------------------------------------------
# _summarize_field_options
# ---------------------------------------------------------------------------

def test_number_precision():
    assert summarize("number", {"precision": 2}) == "precision: 2"
    assert summarize("percent", {"precision": 0}) == "precision: 0"


def test_currency_symbol_and_precision():
    assert summarize("currency", {"symbol": "$", "precision": 2}) == "$ · precision: 2"


def test_date_and_datetime_formats():
    assert summarize("date", {"dateFormat": {"name": "local", "format": "l"}}) == "local"
    out = summarize("dateTime", {
        "dateFormat": {"name": "local"},
        "timeFormat": {"name": "24hour"},
        "timeZone": "America/New_York",
    })
    assert out == "local · 24hour · America/New_York"


def test_rating_and_checkbox():
    assert summarize("rating", {"max": 5, "icon": "star"}) == "max 5 · star"
    assert summarize("checkbox", {"icon": "check", "color": "greenBright"}) == "check · greenBright"


def test_selects_list_every_choice():
    choices = [{"name": f"Opt{i}"} for i in range(7)]
    out = summarize("singleSelect", {"choices": choices})
    assert out == "Choices: Opt0, Opt1, Opt2, Opt3, Opt4, Opt5, Opt6"
    # No truncation marker
    assert "more" not in out and "..." not in out


def test_record_links_flags():
    assert summarize("multipleRecordLinks", {"linkedTableId": "tblXXX"}) == "→ `tblXXX`"
    out = summarize("multipleRecordLinks", {
        "linkedTableId": "tblXXX", "isReversed": True, "prefersSingleRecordLink": True,
    })
    assert out == "→ `tblXXX` (reversed, single)"


def test_rollup_lookup_count():
    assert summarize("count", {"recordLinkFieldId": "fldLink"}) == "via `fldLink`"
    out = summarize("rollup", {
        "recordLinkFieldId": "fldLink",
        "fieldIdInLinkedTable": "fldRemote",
        "result": {"type": "number"},
    })
    assert out == "via `fldLink` → `fldRemote` · result: number"
    out = summarize("multipleLookupValues", {
        "recordLinkFieldId": "fldLink",
        "fieldIdInLinkedTable": "fldRemote",
        "result": {"type": "singleLineText"},
    })
    assert out == "via `fldLink` → `fldRemote` · result: singleLineText"


def test_formula_result_type():
    assert summarize("formula", {"result": {"type": "number"}}) == "result: number"


def test_optionless_types_return_empty():
    for ftype in ("singleLineText", "email", "url", "phoneNumber", "barcode",
                  "autoNumber", "button", "createdBy", "richText"):
        assert summarize(ftype, {}) == ""


# ---------------------------------------------------------------------------
# format_schema_as_markdown
# ---------------------------------------------------------------------------

LONG_DESC = "x" * 250  # well over the old 100-char cap

SCHEMA = {
    "tables": [
        {
            "id": "tblA",
            "name": "Applicant",
            "description": "",
            "fields": [
                {"id": "fld1", "name": "Score", "type": "number", "options": {"precision": 1}},
                {"id": "fld2", "name": "Fee", "type": "currency",
                 "options": {"symbol": "£", "precision": 2}},
                {"id": "fld3", "name": "Applied", "type": "date",
                 "options": {"dateFormat": {"name": "iso"}}},
                {"id": "fld4", "name": "Stage", "type": "singleSelect",
                 "options": {"choices": [{"name": f"S{i}"} for i in range(6)]}},
                {"id": "fld5", "name": "Cohort", "type": "multipleRecordLinks",
                 "options": {"linkedTableId": "tblB", "isReversed": True}},
                {"id": "fld6", "name": "Total", "type": "rollup",
                 "options": {"recordLinkFieldId": "fld5",
                             "fieldIdInLinkedTable": "fldX", "result": {"type": "number"}}},
                {"id": "fld7", "name": "Notes", "type": "multilineText",
                 "description": LONG_DESC},
            ],
            "views": [{"id": "viw1", "name": "All", "type": "grid"}],
        }
    ]
}


def test_markdown_has_options_column():
    md = render(SCHEMA, "appXXX", "Test Base")
    assert "| # | Field Name | Field ID | Type | Options | Description |" in md


def test_markdown_renders_option_summaries():
    md = render(SCHEMA, "appXXX", "Test Base")
    assert "precision: 1" in md
    assert "£ · precision: 2" in md
    assert "iso" in md
    assert "Choices: S0, S1, S2, S3, S4, S5" in md
    assert "→ `tblB` (reversed)" in md
    assert "via `fld5` → `fldX` · result: number" in md


def test_markdown_does_not_truncate():
    md = render(SCHEMA, "appXXX", "Test Base")
    # Long description appears in full, no ellipsis
    assert LONG_DESC in md
    assert "..." not in md
    assert "more" not in md


def test_markdown_header_has_totals():
    md = render(SCHEMA, "appXXX", "Test Base")
    # one table, seven fields, one view
    assert "**Tables:** 1 · **Fields:** 7 · **Views:** 1" in md


def test_markdown_per_table_stats_line():
    md = render(SCHEMA, "appXXX", "Test Base")
    # primaryFieldId absent -> falls back to first field "Score"
    assert "**Primary field:** Score · **Fields:** 7 · **Views:** 1" in md
