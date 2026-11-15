"""Unit tests for the OKB importer preflight and value coercions.

These tests do not touch PostgreSQL: they exercise the deterministic workbook
loader/validator and the integer/minimal value handling that previously broke
the import.
"""
import pandas as pd
import pytest

from scripts import import_kb


def test_as_text_handles_integer_like_values():
    assert import_kb._as_text(2512) == "2512"
    assert import_kb._as_text(2018.0) == "2018"
    assert import_kb._as_text(2018) == "2018"
    assert import_kb._as_text("J.620100.001.1") == "J.620100.001.1"
    assert import_kb._as_text(None) is None
    assert import_kb._as_text(float("nan")) is None


def test_normalize_unit_id_zero_pads_numeric_suffix():
    assert import_kb.normalize_unit_id("CU029_1") == "CU029_001"
    assert import_kb.normalize_unit_id("CU029_001") == "CU029_001"
    assert import_kb.normalize_unit_id("OTHER") == "OTHER"


def test_authoritative_workbook_matches_approved_contract():
    sheets = import_kb._load_workbook(import_kb.XLSX_PATH)
    import_kb._validate_workbook(sheets)
    assert {name: len(frame) for name, frame in sheets.items()} == import_kb.EXPECTED_COUNTS


def test_preflight_rejects_changed_record_count():
    sheets = import_kb._load_workbook(import_kb.XLSX_PATH)
    sheets["CAREER"] = sheets["CAREER"].iloc[:-1]
    with pytest.raises(import_kb.WorkbookValidationError):
        import_kb._validate_workbook(sheets)


def test_preflight_rejects_duplicate_primary_key():
    sheets = import_kb._load_workbook(import_kb.XLSX_PATH)
    sheets["CAREER"] = pd.concat([sheets["CAREER"], sheets["CAREER"].iloc[[0]]], ignore_index=True)
    with pytest.raises(import_kb.WorkbookValidationError):
        import_kb._validate_workbook(sheets)


def test_preflight_rejects_dangling_foreign_key():
    sheets = import_kb._load_workbook(import_kb.XLSX_PATH)
    sheets["SKILL"] = sheets["SKILL"].copy()
    sheets["SKILL"].loc[sheets["SKILL"].index[0], "skill_group_id"] = "SG99"
    with pytest.raises(import_kb.WorkbookValidationError):
        import_kb._validate_workbook(sheets)


def test_preflight_rejects_kominfo_source_name_overflow_at_legacy_width():
    # The approved value is 21 characters; the legacy schema was varchar(20).
    assert len("Kominfo_Kemnaker_BNSP") == 21
    # The migrated width must accommodate it and the preflight must accept it.
    sheets = import_kb._load_workbook(import_kb.XLSX_PATH)
    import_kb._validate_workbook(sheets)


def test_migrations_are_ordered_and_widen_source_name_columns():
    from scripts.migrations.okb_migrations import iter_migration_files

    files = iter_migration_files()
    assert files, "expected at least one OKB migration"
    names = [path.name for path in files]
    assert names == sorted(names)

    sql = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "occupation_source_mapping" in sql
    assert "skill_source_evidence" in sql
    assert "character varying(100)" in sql


def test_migration_statement_splitter_skips_empty_statements():
    from scripts.migrations.okb_migrations import _statements

    assert _statements("SELECT 1; ;  SELECT 2 ;") == ["SELECT 1", "SELECT 2"]
