"""Import the approved Occupational Knowledge Base workbook into PostgreSQL.

Two modes:

* append (default) - refuse to write unless every OKB table is empty.
* ``--rebuild``    - delete the 16 OKB tables inside the import transaction,
  reset their serial sequences, then import. This is the approved workflow for
  ``career_intelligence_e2e_test``.

Safety is fail-closed: the importer only runs against a loopback host and the
exact database ``career_intelligence_e2e_test``, with an explicit opt-in via
``CAREER_E2E_ISOLATED_DB_OK``. ``career_intelligence_main`` can never be
targeted. The whole run - schema migrations, rebuild deletes, and data load -
executes in a single transaction, so any failure rolls back atomically.
"""
import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # make `app` importable
from sqlalchemy import text

from app.core.db import get_engine

try:  # imported both as a package module and as a directly executed script
    from scripts.migrations.okb_migrations import apply_okb_migrations
except ImportError:  # pragma: no cover - direct script execution fallback
    from migrations.okb_migrations import apply_okb_migrations

BASE_DIR = Path(__file__).resolve().parents[2]
XLSX_PATH = BASE_DIR / "data" / "occupational_knowledge_base_verified_v1_0.xlsx"

ALLOWED_E2E_DB = "career_intelligence_e2e_test"
E2E_OPTIN_ENV = "CAREER_E2E_ISOLATED_DB_OK"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Validation targets from the approved workbook. These are guard rails: the
# import refuses to run if the authoritative file no longer matches them.
EXPECTED_COUNTS = {
    "CAREER": 10,
    "OCCUPATION": 23,
    "CAREER_OCCUPATION": 27,
    "SKILL_GROUP": 17,
    "SKILL": 87,
    "CAREER_SKILL": 155,
    "SKKNI_STANDARD": 9,
    "COMPETENCY_UNIT": 146,
    "OCCUPATION_COMPETENCY": 10,
    "COMPETENCY_SKILL": 79,
    "OCCUPATION_SOURCE_MAPPING": 25,
    "TECHNOLOGY": 120,
    "TASK": 221,
    "PROVENANCE": 14,
    "SKILL_SOURCE_EVIDENCE": 97,
    "STANDARD_COVERAGE": 9,
}

# Child-to-parent delete order for a reproducible rebuild. user_* tables are
# never touched; the rebuild refuses to run if user_skills would be orphaned.
REBUILD_DELETE_ORDER = [
    "skill_source_evidence",
    "occupation_source_mapping",
    "competency_skills",
    "occupation_competencies",
    "career_skills",
    "career_occupations",
    "tasks",
    "technologies",
    "competency_units",
    "skkni_standards",
    "skills",
    "skill_groups",
    "occupations",
    "careers",
    "provenance",
    "etl_transform_log",
]

SERIAL_SEQUENCES = [
    "career_occupations_id_seq",
    "occupation_competencies_id_seq",
    "etl_transform_log_log_id_seq",
]

PRIMARY_KEYS = {
    "CAREER": "career_id",
    "OCCUPATION": "occupation_id",
    "SKILL_GROUP": "skill_group_id",
    "SKILL": "skill_id",
    "CAREER_SKILL": "relationship_id",
    "SKKNI_STANDARD": "standard_id",
    "COMPETENCY_UNIT": "unit_id",
    "OCCUPATION_SOURCE_MAPPING": "mapping_id",
    "TECHNOLOGY": "technology_id",
    "TASK": "task_id",
    "PROVENANCE": "provenance_id",
    "SKILL_SOURCE_EVIDENCE": "evidence_id",
    "STANDARD_COVERAGE": "standard_id",
}

COMPOSITE_KEYS = {
    "CAREER_OCCUPATION": ["career_id", "occupation_id"],
    "OCCUPATION_COMPETENCY": ["occupation_id", "standard_id"],
    "CAREER_SKILL": ["career_id", "skill_id"],
    "COMPETENCY_SKILL": ["unit_id", "skill_id"],
}

FOREIGN_KEYS = [
    ("CAREER_OCCUPATION", "career_id", "CAREER", "career_id"),
    ("CAREER_OCCUPATION", "occupation_id", "OCCUPATION", "occupation_id"),
    ("SKILL", "skill_group_id", "SKILL_GROUP", "skill_group_id"),
    ("CAREER_SKILL", "career_id", "CAREER", "career_id"),
    ("CAREER_SKILL", "skill_id", "SKILL", "skill_id"),
    ("COMPETENCY_UNIT", "standard_id", "SKKNI_STANDARD", "standard_id"),
    ("OCCUPATION_COMPETENCY", "occupation_id", "OCCUPATION", "occupation_id"),
    ("OCCUPATION_COMPETENCY", "standard_id", "SKKNI_STANDARD", "standard_id"),
    ("COMPETENCY_SKILL", "unit_id", "COMPETENCY_UNIT", "unit_id"),
    ("COMPETENCY_SKILL", "skill_id", "SKILL", "skill_id"),
    ("OCCUPATION_SOURCE_MAPPING", "occupation_id", "OCCUPATION", "occupation_id"),
    ("TECHNOLOGY", "occupation_id", "OCCUPATION", "occupation_id"),
    ("TASK", "occupation_id", "OCCUPATION", "occupation_id"),
    ("SKILL_SOURCE_EVIDENCE", "skill_id", "SKILL", "skill_id"),
    ("STANDARD_COVERAGE", "standard_id", "SKKNI_STANDARD", "standard_id"),
]

REQUIRED_NON_NULL = {
    "CAREER": ["career_id", "canonical_name", "domain"],
    "OCCUPATION": ["occupation_id", "canonical_name", "classification"],
    "CAREER_OCCUPATION": ["career_id", "occupation_id", "mapping_method", "confidence"],
    "SKILL_GROUP": ["skill_group_id", "name"],
    "SKILL": ["skill_id", "canonical_name", "skill_group_id", "status"],
    "CAREER_SKILL": [
        "relationship_id", "career_id", "skill_id", "evidence_source",
        "evidence_class", "mapping_method", "confidence",
    ],
    "SKKNI_STANDARD": ["standard_id", "number", "year", "title", "field", "status"],
    "COMPETENCY_UNIT": ["unit_id", "standard_id", "code", "title"],
    "OCCUPATION_COMPETENCY": ["occupation_id", "standard_id", "mapping_confidence"],
    "COMPETENCY_SKILL": ["relationship_id", "unit_id", "skill_id", "mapping_method"],
    "OCCUPATION_SOURCE_MAPPING": [
        "mapping_id", "occupation_id", "source_name", "source_code",
        "source_title", "mapping_method", "confidence", "source_scope",
    ],
    "TECHNOLOGY": [
        "technology_id", "technology_name", "technology_type", "occupation_id",
        "source", "source_period", "geography", "frequency_pct",
    ],
    "TASK": [
        "task_id", "occupation_id", "source_code", "task_description",
        "task_category", "importance", "source", "source_period", "geography",
    ],
    "PROVENANCE": [
        "provenance_id", "source_name", "document_id", "document_title",
        "version_or_year", "source_type",
    ],
    "SKILL_SOURCE_EVIDENCE": [
        "evidence_id", "skill_id", "source_name", "source_reference",
        "evidence_type", "confidence",
    ],
    "STANDARD_COVERAGE": ["standard_id", "number", "year"],
}

# Columns whose declared width is smaller than text. Kept explicit so the
# preflight catches overflow before PostgreSQL does.
VARCHAR_LIMITS = {
    "career_id": 10,
    "occupation_id": 10,
    "skill_id": 10,
    "skill_group_id": 10,
    "relationship_id": 10,
    "standard_id": 10,
    "mapping_id": 10,
    "technology_id": 10,
    "task_id": 10,
    "provenance_id": 10,
    "evidence_id": 10,
    "unit_id": 15,
    "source_name": 100,
    "mapping_method": 50,
    "confidence": 20,
    "evidence_class": 30,
    "mapping_basis": 50,
    "unit_inventory_status": 30,
}


class ImportKBSafetyError(RuntimeError):
    """Fail-closed safety violation for KB importer."""


class WorkbookValidationError(ValueError):
    """The authoritative workbook no longer matches its approved contract."""


def _validate_isolated_db_safety(engine) -> None:
    optin = os.environ.get(E2E_OPTIN_ENV, "").strip()
    if optin != ALLOWED_E2E_DB:
        raise ImportKBSafetyError(
            "KB import requires explicit opt-in via CAREER_E2E_ISOLATED_DB_OK=career_intelligence_e2e_test."
        )

    url = engine.url
    host = (url.host or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise ImportKBSafetyError("KB import requires a loopback database host.")

    db_name = url.database
    if db_name != ALLOWED_E2E_DB:
        raise ImportKBSafetyError(
            "KB import only allowed on career_intelligence_e2e_test database; "
            "career_intelligence_main is never an import target."
        )

    with engine.connect() as connection:
        current_db = connection.execute(text("SELECT current_database()")).scalar_one()
    if current_db != ALLOWED_E2E_DB:
        raise ImportKBSafetyError(
            "KB import only allowed on career_intelligence_e2e_test database."
        )


def _as_text(value):
    """Convert workbook scalar values (including Python/NumPy ints) to TEXT."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_unit_id(uid):
    """Zero-pad the numeric suffix of ``CU<digits>_<digits>`` identifiers."""
    match = re.match(r"^(CU\d+_)(\d+)$", str(uid))
    if not match:
        return uid
    prefix, number = match.groups()
    return f"{prefix}{int(number):03d}"


def _load_workbook(path: Path) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(path)
    return {sheet: pd.read_excel(xls, sheet).dropna(how="all") for sheet in EXPECTED_COUNTS}


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise WorkbookValidationError(message)


def _validate_workbook(sheets: dict[str, pd.DataFrame]) -> None:
    # 1. Exact approved record counts.
    for sheet, expected in EXPECTED_COUNTS.items():
        _assert(
            len(sheets[sheet]) == expected,
            f"{sheet} has {len(sheets[sheet])} rows, expected {expected}",
        )

    # 2. Primary-key uniqueness and non-null.
    for sheet, key in PRIMARY_KEYS.items():
        frame = sheets[sheet]
        _assert(frame[key].notna().all(), f"{sheet}.{key} contains nulls")
        duplicates = frame[key][frame[key].duplicated()].tolist()
        _assert(not duplicates, f"{sheet}.{key} has duplicate keys: {duplicates[:5]}")

    # 3. Composite-key uniqueness (unit_id normalized first).
    competency_units = sheets["COMPETENCY_UNIT"].copy()
    competency_units["normalized_unit_id"] = competency_units["unit_id"].map(normalize_unit_id)
    competency_skills = sheets["COMPETENCY_SKILL"].copy()
    competency_skills["normalized_unit_id"] = competency_skills["unit_id"].map(normalize_unit_id)
    normalized_sheets = {
        **sheets,
        "COMPETENCY_UNIT_NORMALIZED": competency_units,
        "COMPETENCY_SKILL_NORMALIZED": competency_skills,
    }
    for sheet, columns in COMPOSITE_KEYS.items():
        frame = normalized_sheets.get(f"{sheet}_NORMALIZED", sheets[sheet])
        columns = ["normalized_unit_id" if column == "unit_id" else column for column in columns]
        duplicates = frame[frame.duplicated(subset=columns, keep=False)]
        _assert(
            duplicates.empty,
            f"{sheet} has duplicate composite keys ({columns}): "
            f"{duplicates[columns].drop_duplicates().to_dict('records')[:5]}",
        )

    # 4. Foreign-key resolution (unit_id normalized where relevant).
    for sheet, column, parent_sheet, parent_column in FOREIGN_KEYS:
        child = normalized_sheets.get(f"{sheet}_NORMALIZED", sheets[sheet])
        child_column = "normalized_unit_id" if column == "unit_id" else column
        parent = normalized_sheets.get(f"{parent_sheet}_NORMALIZED", sheets[parent_sheet])
        parent_column = "normalized_unit_id" if parent_column == "unit_id" else parent_column
        child_values = set(child[child_column].dropna().astype(str))
        parent_values = set(parent[parent_column].dropna().astype(str))
        dangling = sorted(child_values - parent_values)
        _assert(
            not dangling,
            f"{sheet}.{column} -> {parent_sheet}.{parent_column} has dangling "
            f"references: {dangling[:10]}",
        )

    # 5. Every non-null required value is present.
    for sheet, columns in REQUIRED_NON_NULL.items():
        frame = sheets[sheet]
        for column in columns:
            _assert(not frame[column].isna().any(), f"{sheet}.{column} contains nulls")

    # 6. Text fields fit their declared PostgreSQL widths.
    for sheet, frame in sheets.items():
        for column in frame.columns:
            limit = VARCHAR_LIMITS.get(str(column))
            if not limit:
                continue
            too_long = frame[column].dropna().astype(str)
            too_long = too_long[too_long.str.len() > limit]
            _assert(
                too_long.empty,
                f"{sheet}.{column} exceeds varchar({limit}): {too_long.head(3).tolist()}",
            )

    # 7. Denormalized skill_name columns must agree with the canonical SKILL
    #    table, otherwise dropping them on import would lose information.
    skill_names = dict(zip(sheets["SKILL"]["skill_id"], sheets["SKILL"]["canonical_name"]))
    for sheet in ("CAREER_SKILL", "COMPETENCY_SKILL", "SKILL_SOURCE_EVIDENCE"):
        frame = sheets[sheet]
        mismatches = [
            (row["skill_id"], row.get("skill_name"))
            for _, row in frame.iterrows()
            if str(row.get("skill_name")) != str(skill_names.get(row["skill_id"]))
        ]
        _assert(
            not mismatches,
            f"{sheet}.skill_name disagrees with SKILL.canonical_name: {mismatches[:3]}",
        )

    # 8. STANDARD_COVERAGE must map one-to-one onto SKKNI_STANDARD.
    coverage_ids = set(sheets["STANDARD_COVERAGE"]["standard_id"].astype(str))
    standard_ids = set(sheets["SKKNI_STANDARD"]["standard_id"].astype(str))
    _assert(coverage_ids == standard_ids, "STANDARD_COVERAGE and SKKNI_STANDARD ids differ")


def _check_careers_empty(engine) -> None:
    """Fail-closed guard for the default append-only import.

    Retained as a public helper: the append workflow must never add a second
    OKB on top of an existing one. ``--rebuild`` is the only path that may
    replace data.
    """
    with engine.connect() as connection:
        career_count = connection.execute(text("SELECT count(*) FROM careers")).scalar_one()
    if int(career_count) > 0:
        raise ImportKBSafetyError(
            "KB import refused: careers table already contains data; "
            "append-only import is not permitted. Use --rebuild for the "
            "approved rebuild workflow."
        )


def _check_append_target_empty(conn) -> None:
    non_empty = []
    for table in REBUILD_DELETE_ORDER:
        count = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        if int(count) > 0:
            non_empty.append(f"{table}={count}")
    if non_empty:
        raise ImportKBSafetyError(
            "KB append import refused: OKB tables already contain data "
            f"({', '.join(non_empty)}). Use --rebuild for the approved rebuild workflow."
        )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Import the approved OKB workbook.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="delete and rebuild the 16 OKB tables inside the import transaction",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    _run_import(rebuild=args.rebuild)


def _run_import(rebuild: bool = False):
    engine = get_engine()
    _validate_isolated_db_safety(engine)

    if not rebuild:
        _check_careers_empty(engine)

    sheets = _load_workbook(XLSX_PATH)
    _validate_workbook(sheets)

    transform_log_rows = []

    def log_transform(table, pk, field, raw, transformed, ttype, note=None):
        transform_log_rows.append({
            "table_name": table, "record_pk": str(pk), "field_name": field,
            "raw_value": None if pd.isna(raw) else str(raw),
            "transformed_value": None if pd.isna(transformed) else str(transformed),
            "transform_type": ttype, "notes": note,
        })

    with engine.begin() as conn:
        applied = apply_okb_migrations(conn)
        print(f"migrations applied: {applied}")

        if rebuild:
            user_refs = conn.execute(text("SELECT count(*) FROM user_skills")).scalar_one()
            if int(user_refs) > 0:
                raise ImportKBSafetyError(
                    "Refusing OKB rebuild: user_skills still references OKB skills "
                    f"({user_refs} row(s)). Clear user data first or use an empty test database."
                )
            for table in REBUILD_DELETE_ORDER:
                conn.execute(text(f'DELETE FROM "{table}"'))
            for sequence in SERIAL_SEQUENCES:
                conn.execute(text(f"ALTER SEQUENCE IF EXISTS {sequence} RESTART WITH 1"))
            print(f"rebuild: cleared {len(REBUILD_DELETE_ORDER)} OKB tables")
        else:
            _check_append_target_empty(conn)

        # ---------- 1. skill_groups ----------
        sg = sheets["SKILL_GROUP"]
        sg.to_sql("skill_groups", conn, if_exists="append", index=False)
        print(f"skill_groups: {len(sg)} rows")

        # ---------- 2. careers ----------
        career = sheets["CAREER"]
        career.to_sql("careers", conn, if_exists="append", index=False)
        print(f"careers: {len(career)} rows")

        # ---------- 3. occupations ----------
        occupation = sheets["OCCUPATION"]
        occupation.to_sql("occupations", conn, if_exists="append", index=False)
        print(f"occupations: {len(occupation)} rows")

        # ---------- 4. skills ----------
        skill = sheets["SKILL"]
        skill.to_sql("skills", conn, if_exists="append", index=False)
        print(f"skills: {len(skill)} rows")

        # ---------- 5. career_occupations ----------
        co = sheets["CAREER_OCCUPATION"]
        co.to_sql("career_occupations", conn, if_exists="append", index=False)
        print(f"career_occupations: {len(co)} rows")

        # ---------- 6. career_skills ----------
        cs = sheets["CAREER_SKILL"].drop(columns=["skill_name"])
        cs.to_sql("career_skills", conn, if_exists="append", index=False)
        print(f"career_skills: {len(cs)} rows")

        # ---------- 7. skkni_standards (merge STANDARD_COVERAGE) ----------
        skkni = sheets["SKKNI_STANDARD"]
        cov = sheets["STANDARD_COVERAGE"].rename(columns={"action": "coverage_action_note"})
        skkni_merged = skkni.merge(
            cov[["standard_id", "unit_inventory_status", "unit_count_in_dataset",
                 "evidence_basis", "coverage_action_note"]],
            on="standard_id", how="left"
        )
        skkni_merged.to_sql("skkni_standards", conn, if_exists="append", index=False)
        print(f"skkni_standards: {len(skkni_merged)} rows")

        # ---------- 8. competency_units (padding normalization) ----------
        cu = sheets["COMPETENCY_UNIT"].copy()
        cu["raw_unit_id"] = cu["unit_id"]
        cu["unit_id"] = cu["raw_unit_id"].apply(normalize_unit_id)
        changed = cu[cu["unit_id"] != cu["raw_unit_id"]]
        for _, r in changed.iterrows():
            log_transform("competency_units", r["unit_id"], "unit_id", r["raw_unit_id"], r["unit_id"],
                          "unit_id_padding_fix", "zero-padding normalized to match COMPETENCY_UNIT convention")
        cu = cu[["unit_id", "standard_id", "code", "title"]]
        cu.to_sql("competency_units", conn, if_exists="append", index=False)
        print(f"competency_units: {len(cu)} rows ({len(changed)} padding-normalized)")

        valid_unit_ids = set(cu["unit_id"])

        # ---------- 9. occupation_competencies ----------
        oc = sheets["OCCUPATION_COMPETENCY"]
        oc.to_sql("occupation_competencies", conn, if_exists="append", index=False)
        print(f"occupation_competencies: {len(oc)} rows")

        # ---------- 10. competency_skills (normalize unit_id FKs) ----------
        ck = sheets["COMPETENCY_SKILL"].drop(columns=["skill_name"]).copy()
        ck["raw_unit_id_ref"] = ck["unit_id"]
        ck["unit_id"] = ck["unit_id"].apply(normalize_unit_id)
        unresolved = ck[~ck["unit_id"].isin(valid_unit_ids)]
        if len(unresolved):
            raise ValueError(f"Unresolved unit_id references after normalization: {unresolved['unit_id'].tolist()}")
        fixed = ck[ck["unit_id"] != ck["raw_unit_id_ref"]]
        for _, r in fixed.iterrows():
            log_transform("competency_skills", r["relationship_id"], "unit_id",
                          r["raw_unit_id_ref"], r["unit_id"], "unit_id_padding_fix",
                          "FK repointed to normalized competency_units.unit_id")
        ck = ck[["relationship_id", "unit_id", "skill_id", "mapping_method"]]
        ck.to_sql("competency_skills", conn, if_exists="append", index=False)
        print(f"competency_skills: {len(ck)} rows ({len(fixed)} FK-repointed)")

        # ---------- 11. technologies ----------
        tech = sheets["TECHNOLOGY"]
        tech.to_sql("technologies", conn, if_exists="append", index=False)
        print(f"technologies: {len(tech)} rows")

        # ---------- 12. tasks (integer source_code -> TEXT) ----------
        task = sheets["TASK"].copy()
        task["source_code"] = task["source_code"].map(_as_text)
        task.to_sql("tasks", conn, if_exists="append", index=False)
        print(f"tasks: {len(task)} rows")

        # ---------- 13. provenance (integer year -> TEXT) ----------
        prov = sheets["PROVENANCE"].copy()
        prov["version_or_year"] = prov["version_or_year"].map(_as_text)
        prov.to_sql("provenance", conn, if_exists="append", index=False)
        print(f"provenance: {len(prov)} rows")

        # ---------- 14. occupation_source_mapping (provenance derivation) ----------
        osm = sheets["OCCUPATION_SOURCE_MAPPING"].copy()
        osm["source_code"] = osm["source_code"].map(_as_text)
        prov_df = prov.copy()

        def find_provenance(needle: str):
            names = prov_df["source_name"].astype(str)
            match = prov_df[names.str.contains(needle, case=False, regex=False, na=False)]
            return match.iloc[0]["provenance_id"] if len(match) else None

        def basis(pid):
            return "derived-deterministic" if pid else "evidence-unavailable-ambiguous-source"

        onet_prov = dict(zip(
            prov_df.loc[prov_df.source_name == "O*NET", "document_id"],
            prov_df.loc[prov_df.source_name == "O*NET", "provenance_id"],
        ))
        kbji_prov_id = find_provenance("KBJI")
        kominfo_prov_id = find_provenance("Kominfo")
        esco_prov_id = prov_df.loc[prov_df.source_name == "ESCO", "provenance_id"]
        esco_prov_id = esco_prov_id.iloc[0] if len(esco_prov_id) else None

        if kominfo_prov_id is None:
            raise WorkbookValidationError("No Kominfo provenance record found in PROVENANCE.")

        def derive_osm_provenance(row):
            name = str(row["source_name"])
            if name.startswith("Kominfo"):
                return kominfo_prov_id, basis(kominfo_prov_id)
            if name == "O*NET":
                pid = onet_prov.get(row["source_code"])
                return pid, basis(pid)
            if name == "KBJI":
                return kbji_prov_id, basis(kbji_prov_id)
            if name == "ESCO":
                return esco_prov_id, basis(esco_prov_id)
            # IndoTask is intentionally left ambiguous: the workbook does not
            # disambiguate the report (P012) from the profile report (P013).
            return None, "evidence-unavailable-ambiguous-source"

        osm[["provenance_id", "mapping_basis"]] = osm.apply(
            lambda r: pd.Series(derive_osm_provenance(r)), axis=1
        )
        for _, r in osm.iterrows():
            log_transform("occupation_source_mapping", r["mapping_id"], "provenance_id",
                          None, r["provenance_id"], "provenance_fk_derivation",
                          f"basis={r['mapping_basis']}, source={r['source_name']}")
        unresolved_osm = osm[
            osm["source_name"].astype(str).str.startswith("Kominfo") & osm["provenance_id"].isna()
        ]
        if len(unresolved_osm):
            raise WorkbookValidationError(
                f"Kominfo source mappings without provenance: {unresolved_osm['mapping_id'].tolist()}"
            )
        osm.to_sql("occupation_source_mapping", conn, if_exists="append", index=False)
        n_null = int(osm["provenance_id"].isna().sum())
        print(f"occupation_source_mapping: {len(osm)} rows ({n_null} intentionally NULL - IndoTask)")

        # ---------- 15. skill_source_evidence (provenance derivation) ----------
        sse = sheets["SKILL_SOURCE_EVIDENCE"].drop(columns=["skill_name"]).copy()

        skkni_prefix_to_standard = {
            "J.620100": "SK01", "J.62SQA00": "SK02", "J.63SAM00": "SK03",
            "J.62DMS00": "SK04", "J.62DMI00": "SK05", "J.62KAM00": "SK07",
        }
        skkni_std_df = skkni_merged[["standard_id", "number", "year"]].copy()
        skkni_std_df["doc_key"] = skkni_std_df["number"].astype(str) + "/" + skkni_std_df["year"].astype(str)
        std_to_prov = {}
        for _, r in skkni_std_df.iterrows():
            match = prov_df[(prov_df.source_name == "SKKNI") & (prov_df.document_id.str.contains(r["doc_key"], na=False))]
            if len(match):
                std_to_prov[r["standard_id"]] = match.iloc[0]["provenance_id"]

        def derive_sse_provenance(row):
            name = str(row["source_name"])
            if name.startswith("Kominfo"):
                return kominfo_prov_id, basis(kominfo_prov_id)
            if name == "O*NET":
                pid = onet_prov.get(row["source_reference"])
                return pid, basis(pid)
            if name == "SKKNI":
                ref = str(row["source_reference"])
                prefix = ".".join(ref.split(".")[:2])
                std_id = skkni_prefix_to_standard.get(prefix)
                pid = std_to_prov.get(std_id) if std_id else None
                return pid, basis(pid)
            if name == "ESCO":
                return esco_prov_id, basis(esco_prov_id)
            if name == "KBJI":
                return kbji_prov_id, basis(kbji_prov_id)
            return None, "evidence-unavailable-ambiguous-source"

        sse[["provenance_id", "mapping_basis"]] = sse.apply(
            lambda r: pd.Series(derive_sse_provenance(r)), axis=1
        )
        for _, r in sse.iterrows():
            log_transform("skill_source_evidence", r["evidence_id"], "provenance_id",
                          None, r["provenance_id"], "provenance_fk_derivation",
                          f"basis={r['mapping_basis']}, source={r['source_name']}")
        unresolved_sse = sse[
            sse["source_name"].astype(str).str.startswith("Kominfo") & sse["provenance_id"].isna()
        ]
        if len(unresolved_sse):
            raise WorkbookValidationError(
                f"Kominfo skill evidence without provenance: {unresolved_sse['evidence_id'].tolist()}"
            )
        sse.to_sql("skill_source_evidence", conn, if_exists="append", index=False)
        n_null_sse = int(sse["provenance_id"].isna().sum())
        print(f"skill_source_evidence: {len(sse)} rows ({n_null_sse} intentionally NULL - IndoTask)")

        # ---------- 16. etl_transform_log ----------
        log_columns = [
            "table_name", "record_pk", "field_name", "raw_value",
            "transformed_value", "transform_type", "notes",
        ]
        log_df = pd.DataFrame(transform_log_rows, columns=log_columns)
        log_df.to_sql("etl_transform_log", conn, if_exists="append", index=False)
        print(f"etl_transform_log: {len(log_df)} rows")

        # ---------- post-insert count assertions ----------
        expected_tables = {
            "careers": EXPECTED_COUNTS["CAREER"],
            "occupations": EXPECTED_COUNTS["OCCUPATION"],
            "career_occupations": EXPECTED_COUNTS["CAREER_OCCUPATION"],
            "skill_groups": EXPECTED_COUNTS["SKILL_GROUP"],
            "skills": EXPECTED_COUNTS["SKILL"],
            "career_skills": EXPECTED_COUNTS["CAREER_SKILL"],
            "skkni_standards": EXPECTED_COUNTS["SKKNI_STANDARD"],
            "competency_units": EXPECTED_COUNTS["COMPETENCY_UNIT"],
            "occupation_competencies": EXPECTED_COUNTS["OCCUPATION_COMPETENCY"],
            "competency_skills": EXPECTED_COUNTS["COMPETENCY_SKILL"],
            "occupation_source_mapping": EXPECTED_COUNTS["OCCUPATION_SOURCE_MAPPING"],
            "technologies": EXPECTED_COUNTS["TECHNOLOGY"],
            "tasks": EXPECTED_COUNTS["TASK"],
            "provenance": EXPECTED_COUNTS["PROVENANCE"],
            "skill_source_evidence": EXPECTED_COUNTS["SKILL_SOURCE_EVIDENCE"],
        }
        for table, expected in expected_tables.items():
            actual = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
            if int(actual) != expected:
                raise WorkbookValidationError(
                    f"post-import count mismatch for {table}: got {actual}, expected {expected}"
                )

        print("\nETL COMPLETE.")


if __name__ == "__main__":
    main()
