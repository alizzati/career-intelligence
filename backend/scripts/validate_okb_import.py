"""Post-import validation for the approved Occupational Knowledge Base.

Runs only against ``career_intelligence_e2e_test`` on a loopback host, with the
same fail-closed opt-in as the importer. It never writes to any database.

Checks performed
----------------
1.  Safety: exact database identity and loopback host.
2.  Workbook preflight: the authoritative workbook still matches its contract.
3.  Record counts: DB row counts equal the approved workbook counts.
4.  Structural integrity: primary keys, composite keys, foreign keys, and
    required non-null columns.
5.  Content parity: every workbook row is present in the DB with identical
    domain values (no silently dropped fields or records).
6.  Provenance/evidence links: every non-null ``provenance_id`` resolves, the
    Kominfo rows are deterministically mapped, and only IndoTask rows are
    intentionally left ambiguous.
7.  Runtime retrieval: the public retrieval service returns the full OKB and
    exposes the attribution fields (tasks, technologies, source mappings,
    provenance) required by the agents.
8.  Snapshot coverage: ``compute_okb_snapshot()`` covers every OKB entity and
    relationship and is deterministic.

Exit code 0 means every check passed. Any failure raises and exits non-zero.
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

# ---- Force the approved e2e target before any `app` import ------------------
ALLOWED_E2E_DB = "career_intelligence_e2e_test"
E2E_OPTIN_ENV = "CAREER_E2E_ISOLATED_DB_OK"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

os.environ["CAREER_DB_NAME"] = ALLOWED_E2E_DB
os.environ["CAREER_DB_URL"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

import pandas as pd
from sqlalchemy import text

from app.core.db import get_engine

try:  # imported both as a package module and as a directly executed script
    from scripts.import_kb import (
        EXPECTED_COUNTS,
        XLSX_PATH,
        ImportKBSafetyError,
        WorkbookValidationError,
        _as_text,
        _load_workbook,
        _validate_workbook,
        normalize_unit_id,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from import_kb import (  # type: ignore
        EXPECTED_COUNTS,
        XLSX_PATH,
        ImportKBSafetyError,
        WorkbookValidationError,
        _as_text,
        _load_workbook,
        _validate_workbook,
        normalize_unit_id,
    )

OKB_TABLES = [
    "careers", "occupations", "career_occupations", "skill_groups", "skills",
    "career_skills", "skkni_standards", "competency_units",
    "occupation_competencies", "competency_skills", "technologies", "tasks",
    "provenance", "occupation_source_mapping", "skill_source_evidence",
    "etl_transform_log",
]

# Expected DB counts keyed by table name. STANDARD_COVERAGE is merged into
# skkni_standards; etl_transform_log is import mechanics and has no target.
TABLE_COUNTS = {
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

PRIMARY_KEYS = {
    "careers": "career_id",
    "occupations": "occupation_id",
    "skill_groups": "skill_group_id",
    "skills": "skill_id",
    "career_skills": "relationship_id",
    "skkni_standards": "standard_id",
    "competency_units": "unit_id",
    "occupation_source_mapping": "mapping_id",
    "technologies": "technology_id",
    "tasks": "task_id",
    "provenance": "provenance_id",
    "skill_source_evidence": "evidence_id",
}

COMPOSITE_KEYS = {
    "career_occupations": ["career_id", "occupation_id"],
    "occupation_competencies": ["occupation_id", "standard_id"],
    "career_skills": ["career_id", "skill_id"],
    "competency_skills": ["unit_id", "skill_id"],
}

FOREIGN_KEYS = [
    ("career_occupations", "career_id", "careers", "career_id"),
    ("career_occupations", "occupation_id", "occupations", "occupation_id"),
    ("career_skills", "career_id", "careers", "career_id"),
    ("career_skills", "skill_id", "skills", "skill_id"),
    ("skills", "skill_group_id", "skill_groups", "skill_group_id"),
    ("competency_units", "standard_id", "skkni_standards", "standard_id"),
    ("occupation_competencies", "occupation_id", "occupations", "occupation_id"),
    ("occupation_competencies", "standard_id", "skkni_standards", "standard_id"),
    ("competency_skills", "unit_id", "competency_units", "unit_id"),
    ("competency_skills", "skill_id", "skills", "skill_id"),
    ("technologies", "occupation_id", "occupations", "occupation_id"),
    ("tasks", "occupation_id", "occupations", "occupation_id"),
    ("occupation_source_mapping", "occupation_id", "occupations", "occupation_id"),
    ("occupation_source_mapping", "provenance_id", "provenance", "provenance_id"),
    ("skill_source_evidence", "skill_id", "skills", "skill_id"),
    ("skill_source_evidence", "provenance_id", "provenance", "provenance_id"),
]

REQUIRED_NON_NULL = {
    "careers": ["career_id", "canonical_name", "domain"],
    "occupations": ["occupation_id", "canonical_name", "classification"],
    "career_occupations": ["career_id", "occupation_id", "mapping_method", "confidence"],
    "skill_groups": ["skill_group_id", "name"],
    "skills": ["skill_id", "canonical_name", "skill_group_id", "status"],
    "career_skills": [
        "relationship_id", "career_id", "skill_id", "evidence_source",
        "evidence_class", "mapping_method", "confidence",
    ],
    "skkni_standards": ["standard_id", "number", "year", "title", "field", "status"],
    "competency_units": ["unit_id", "standard_id", "code", "title"],
    "occupation_competencies": ["occupation_id", "standard_id", "mapping_confidence"],
    "competency_skills": ["relationship_id", "unit_id", "skill_id", "mapping_method"],
    "technologies": [
        "technology_id", "technology_name", "technology_type", "occupation_id",
        "source", "source_period", "geography", "frequency_pct",
    ],
    "tasks": [
        "task_id", "occupation_id", "source_code", "task_description",
        "task_category", "importance", "source", "source_period", "geography",
    ],
    "provenance": [
        "provenance_id", "source_name", "document_id", "document_title",
        "version_or_year", "source_type",
    ],
    "occupation_source_mapping": [
        "mapping_id", "occupation_id", "source_name", "source_code",
        "source_title", "mapping_method", "confidence", "source_scope",
        "mapping_basis",
    ],
    "skill_source_evidence": [
        "evidence_id", "skill_id", "source_name", "source_reference",
        "evidence_type", "confidence", "mapping_basis",
    ],
}

OSM_BASIS_ALLOWED = {
    "source-explicit", "derived-manual-match", "derived-deterministic",
    "evidence-unavailable-ambiguous-source",
}
SSE_BASIS_ALLOWED = {
    "derived-deterministic", "derived-manual-default",
    "evidence-unavailable-ambiguous-source",
}

NULL_TEXT = "<NULL>"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
class ValidationError(RuntimeError):
    """One or more OKB validation checks failed."""


def _canon(value) -> str:
    """Canonical string form so Excel ints/floats and DB text/Decimal compare."""
    if value is None:
        return NULL_TEXT
    try:
        if pd.isna(value):
            return NULL_TEXT
    except (TypeError, ValueError):
        pass
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"PASS  {name}")
        else:
            self.failures.append(f"{name}: {detail}")
            print(f"FAIL  {name} :: {detail}")

    def add_failure(self, message: str) -> None:
        self.failures.append(message)

    def finish(self) -> None:
        print("-" * 72)
        if self.failures:
            print(f"VALIDATION FAILED ({len(self.failures)} failure(s))")
            for failure in self.failures:
                print(f"  - {failure}")
            raise ValidationError(f"{len(self.failures)} OKB validation check(s) failed")
        print(f"VALIDATION PASSED ({self.passed} checks)")


# --------------------------------------------------------------------------- #
# safety
# --------------------------------------------------------------------------- #
def _assert_safe_target(conn) -> None:
    optin = os.environ.get(E2E_OPTIN_ENV, "").strip()
    if optin != ALLOWED_E2E_DB:
        raise ImportKBSafetyError(
            f"Validation requires {E2E_OPTIN_ENV}={ALLOWED_E2E_DB}."
        )
    engine = get_engine()
    host = (engine.url.host or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise ImportKBSafetyError("Validation requires a loopback database host.")
    if engine.url.database != ALLOWED_E2E_DB:
        raise ImportKBSafetyError(
            "Validation only allowed on career_intelligence_e2e_test."
        )
    current_db = conn.execute(text("SELECT current_database()")).scalar_one()
    if current_db != ALLOWED_E2E_DB:
        raise ImportKBSafetyError(
            f"Connected to {current_db!r}, expected {ALLOWED_E2E_DB!r}."
        )


# --------------------------------------------------------------------------- #
# workbook expectations (mirror importer transforms)
# --------------------------------------------------------------------------- #
def _expected_frames(sheets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}

    frames["careers"] = sheets["CAREER"][
        ["career_id", "canonical_name", "domain"]
    ].copy()
    frames["occupations"] = sheets["OCCUPATION"][
        ["occupation_id", "canonical_name", "classification"]
    ].copy()
    frames["career_occupations"] = sheets["CAREER_OCCUPATION"][
        ["career_id", "occupation_id", "mapping_method", "confidence"]
    ].copy()
    frames["skill_groups"] = sheets["SKILL_GROUP"][["skill_group_id", "name"]].copy()
    frames["skills"] = sheets["SKILL"][
        ["skill_id", "canonical_name", "skill_group_id", "status"]
    ].copy()
    frames["career_skills"] = sheets["CAREER_SKILL"].drop(columns=["skill_name"]).copy()

    coverage = sheets["STANDARD_COVERAGE"].rename(columns={"action": "coverage_action_note"})
    frames["skkni_standards"] = sheets["SKKNI_STANDARD"].merge(
        coverage[[
            "standard_id", "unit_inventory_status", "unit_count_in_dataset",
            "evidence_basis", "coverage_action_note",
        ]],
        on="standard_id", how="left",
    )

    units = sheets["COMPETENCY_UNIT"].copy()
    units["unit_id"] = units["unit_id"].map(normalize_unit_id)
    frames["competency_units"] = units[["unit_id", "standard_id", "code", "title"]].copy()

    frames["occupation_competencies"] = sheets["OCCUPATION_COMPETENCY"][
        ["occupation_id", "standard_id", "mapping_confidence"]
    ].copy()

    comp_skills = sheets["COMPETENCY_SKILL"].drop(columns=["skill_name"]).copy()
    comp_skills["unit_id"] = comp_skills["unit_id"].map(normalize_unit_id)
    frames["competency_skills"] = comp_skills[
        ["relationship_id", "unit_id", "skill_id", "mapping_method"]
    ].copy()

    frames["technologies"] = sheets["TECHNOLOGY"][
        ["technology_id", "technology_name", "technology_type", "occupation_id",
         "source", "source_period", "geography", "frequency_pct", "evidence_note"]
    ].copy()

    tasks = sheets["TASK"].copy()
    tasks["source_code"] = tasks["source_code"].map(_as_text)
    frames["tasks"] = tasks[[
        "task_id", "occupation_id", "source_code", "task_description",
        "task_category", "importance", "source", "source_period", "geography",
    ]].copy()

    provenance = sheets["PROVENANCE"].copy()
    provenance["version_or_year"] = provenance["version_or_year"].map(_as_text)
    frames["provenance"] = provenance[[
        "provenance_id", "source_name", "document_id", "document_title",
        "version_or_year", "page_or_section", "url", "source_type", "scope_note",
    ]].copy()

    frames["occupation_source_mapping"] = sheets["OCCUPATION_SOURCE_MAPPING"][
        ["mapping_id", "occupation_id", "source_name", "source_code",
         "source_title", "mapping_method", "confidence", "source_scope"]
    ].copy()

    sse = sheets["SKILL_SOURCE_EVIDENCE"].drop(columns=["skill_name"]).copy()
    frames["skill_source_evidence"] = sse[[
        "evidence_id", "skill_id", "source_name", "source_reference",
        "evidence_type", "confidence", "note",
    ]].copy()

    return frames


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def _check_counts(conn, report: Report) -> None:
    for table, expected in TABLE_COUNTS.items():
        actual = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        report.check(
            f"count {table}",
            int(actual) == expected,
            f"got {actual}, expected {expected}",
        )
    log_rows = conn.execute(text("SELECT count(*) FROM etl_transform_log")).scalar_one()
    print(f"INFO  etl_transform_log rows: {log_rows}")


def _check_keys(conn, report: Report) -> None:
    for table, key in PRIMARY_KEYS.items():
        nulls = conn.execute(
            text(f'SELECT count(*) FROM "{table}" WHERE "{key}" IS NULL')
        ).scalar_one()
        total = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        distinct = conn.execute(
            text(f'SELECT count(DISTINCT "{key}") FROM "{table}"')
        ).scalar_one()
        report.check(f"pk {table}.{key}", int(nulls) == 0 and int(distinct) == int(total),
                     f"nulls={nulls}, distinct={distinct}, total={total}")

    for table, columns in COMPOSITE_KEYS.items():
        column_list = ", ".join(f'"{c}"' for c in columns)
        total = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        distinct = conn.execute(
            text(f'SELECT count(*) FROM (SELECT DISTINCT {column_list} FROM "{table}") s')
        ).scalar_one()
        report.check(f"composite {table}({','.join(columns)})",
                     int(distinct) == int(total),
                     f"distinct={distinct}, total={total}")


def _check_foreign_keys(conn, report: Report) -> None:
    for child, column, parent, parent_column in FOREIGN_KEYS:
        dangling = conn.execute(text(
            f'SELECT count(*) FROM "{child}" c '
            f'LEFT JOIN "{parent}" p ON p."{parent_column}" = c."{column}" '
            f'WHERE c."{column}" IS NOT NULL AND p."{parent_column}" IS NULL'
        )).scalar_one()
        report.check(f"fk {child}.{column} -> {parent}.{parent_column}",
                     int(dangling) == 0, f"{dangling} dangling row(s)")


def _check_required(conn, report: Report) -> None:
    for table, columns in REQUIRED_NON_NULL.items():
        for column in columns:
            nulls = conn.execute(text(
                f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL'
            )).scalar_one()
            report.check(f"not-null {table}.{column}", int(nulls) == 0,
                         f"{nulls} null row(s)")


def _check_mapping_basis(conn, report: Report) -> None:
    osm_values = set(conn.execute(text(
        "SELECT DISTINCT mapping_basis FROM occupation_source_mapping"
    )).scalars().all())
    sse_values = set(conn.execute(text(
        "SELECT DISTINCT mapping_basis FROM skill_source_evidence"
    )).scalars().all())
    report.check("osm mapping_basis values", osm_values <= OSM_BASIS_ALLOWED,
                 f"unexpected {sorted(osm_values - OSM_BASIS_ALLOWED)}")
    report.check("sse mapping_basis values", sse_values <= SSE_BASIS_ALLOWED,
                 f"unexpected {sorted(sse_values - SSE_BASIS_ALLOWED)}")


def _check_content_parity(conn, sheets, report: Report) -> None:
    expected_frames = _expected_frames(sheets)
    for table, expected in expected_frames.items():
        columns = list(expected.columns)
        select_list = ", ".join(f'"{c}"' for c in columns)
        db_rows = conn.execute(
            text(f'SELECT {select_list} FROM "{table}"')
        ).mappings().all()
        db_set = {tuple(_canon(row[c]) for c in columns) for row in db_rows}
        wb_set = {
            tuple(_canon(row[c]) for c in columns)
            for _, row in expected.iterrows()
        }
        missing = wb_set - db_set
        extra = db_set - wb_set
        report.check(
            f"content parity {table}",
            not missing and not extra,
            f"missing={len(missing)} extra={len(extra)}; "
            f"sample_missing={list(missing)[:2]} sample_extra={list(extra)[:2]}",
        )


def _check_provenance_links(conn, report: Report) -> None:
    kominfo = conn.execute(text(
        "SELECT provenance_id FROM provenance "
        "WHERE source_name ILIKE '%kominfo%' ORDER BY provenance_id"
    )).scalars().all()
    report.check("single Kominfo provenance record", len(kominfo) == 1, f"{kominfo}")
    kominfo_id = kominfo[0] if kominfo else None

    osm_rows = conn.execute(text(
        "SELECT mapping_id, source_name, provenance_id, mapping_basis "
        "FROM occupation_source_mapping ORDER BY mapping_id"
    )).mappings().all()
    osm_null = [r for r in osm_rows if r["provenance_id"] is None]
    osm_kominfo_null = [
        r for r in osm_rows
        if str(r["source_name"]).startswith("Kominfo") and r["provenance_id"] is None
    ]
    osm_kominfo_all = [r for r in osm_rows if str(r["source_name"]).startswith("Kominfo")]
    report.check("osm Kominfo rows mapped", not osm_kominfo_null,
                 f"{len(osm_kominfo_null)} unmapped")
    report.check(
        "osm Kominfo -> Kominfo provenance",
        all(r["provenance_id"] == kominfo_id and r["mapping_basis"] == "derived-deterministic"
            for r in osm_kominfo_all),
        f"{len(osm_kominfo_all)} Kominfo row(s)",
    )
    report.check("osm null provenance is IndoTask only",
                 len(osm_null) == 2 and all(r["source_name"] == "IndoTask" for r in osm_null),
                 f"nulls={len(osm_null)} sources={[r['source_name'] for r in osm_null]}")

    sse_rows = conn.execute(text(
        "SELECT evidence_id, source_name, provenance_id, mapping_basis "
        "FROM skill_source_evidence ORDER BY evidence_id"
    )).mappings().all()
    sse_null = [r for r in sse_rows if r["provenance_id"] is None]
    sse_kominfo_null = [
        r for r in sse_rows
        if str(r["source_name"]).startswith("Kominfo") and r["provenance_id"] is None
    ]
    sse_kominfo_all = [r for r in sse_rows if str(r["source_name"]).startswith("Kominfo")]
    report.check("sse Kominfo rows mapped", not sse_kominfo_null,
                 f"{len(sse_kominfo_null)} unmapped")
    report.check(
        "sse Kominfo -> Kominfo provenance",
        all(r["provenance_id"] == kominfo_id and r["mapping_basis"] == "derived-deterministic"
            for r in sse_kominfo_all),
        f"{len(sse_kominfo_all)} Kominfo row(s)",
    )
    report.check("sse null provenance is IndoTask only",
                 len(sse_null) == 3 and all(r["source_name"] == "IndoTask" for r in sse_null),
                 f"nulls={len(sse_null)} sources={[r['source_name'] for r in sse_null]}")

    # Every non-null provenance reference in both link tables must resolve.
    for table in ("occupation_source_mapping", "skill_source_evidence"):
        dangling = conn.execute(text(
            f'SELECT count(*) FROM "{table}" t '
            "LEFT JOIN provenance p ON p.provenance_id = t.provenance_id "
            'WHERE t.provenance_id IS NOT NULL AND p.provenance_id IS NULL'
        )).scalar_one()
        report.check(f"provenance reference resolves in {table}", int(dangling) == 0,
                     f"{dangling} dangling reference(s)")

    # Every provenance record must be referenced by at least one link table or
    # by no link table at all -- report coverage for traceability.
    used = conn.execute(text("""
        SELECT p.provenance_id,
               (SELECT count(*) FROM occupation_source_mapping o WHERE o.provenance_id = p.provenance_id) +
               (SELECT count(*) FROM skill_source_evidence s WHERE s.provenance_id = p.provenance_id) AS refs
        FROM provenance p ORDER BY p.provenance_id
    """)).mappings().all()
    print("INFO  provenance reference counts: "
          + ", ".join(f"{r['provenance_id']}={r['refs']}" for r in used))


def _check_runtime_retrieval(report: Report) -> None:
    from app.services import retrieval_service as rs

    careers = rs.get_all_careers()
    report.check("runtime get_all_careers", len(careers) == EXPECTED_COUNTS["CAREER"],
                 f"got {len(careers)}")
    skills = rs.get_all_skills()
    report.check("runtime get_all_skills", len(skills) == EXPECTED_COUNTS["SKILL"],
                 f"got {len(skills)}")

    contexts = []
    for career in careers:
        career_obj = rs.get_career(career.career_id)
        career_skills = rs.get_career_skills(career.career_id)
        links = rs.get_occupations_for_career(career.career_id)
        context = rs.get_occupational_context(career.career_id)
        ok = (
            career_obj is not None
            and context is not None
            and len(career_skills) > 0
            and len(links) > 0
        )
        report.check(f"runtime context {career.career_id}", ok,
                     f"career_skills={len(career_skills)} links={len(links)}")
        if context is not None:
            contexts.append(context)

    all_tasks = [t for ctx in contexts for rows in ctx.tasks.values() for t in rows]
    all_techs = [t for ctx in contexts for rows in ctx.technologies.values() for t in rows]
    all_maps = [m for ctx in contexts for rows in ctx.source_mappings.values() for m in rows]
    all_career_skills = [c for ctx in contexts for c in ctx.career_skills]

    report.check("runtime tasks retrieved", len(all_tasks) > 0, f"{len(all_tasks)}")
    report.check("runtime tasks expose source metadata",
                 any(t.source_code is not None for t in all_tasks)
                 and any(t.source_period is not None for t in all_tasks)
                 and any(t.geography is not None for t in all_tasks),
                 "source_code/source_period/geography")
    report.check("runtime technologies retrieved", len(all_techs) > 0, f"{len(all_techs)}")
    report.check("runtime technologies expose source metadata",
                 any(t.source_period is not None for t in all_techs)
                 and any(t.geography is not None for t in all_techs)
                 and any(t.evidence_note is not None for t in all_techs),
                 "source_period/geography/evidence_note")
    report.check("runtime source mappings retrieved", len(all_maps) > 0, f"{len(all_maps)}")
    report.check("runtime source mappings expose title/scope",
                 any(m.source_title is not None for m in all_maps)
                 and any(m.source_scope is not None for m in all_maps),
                 "source_title/source_scope")
    report.check("runtime career skills retrieved", len(all_career_skills) > 0,
                 f"{len(all_career_skills)}")

    resolved = [m.provenance for m in all_maps if m.provenance is not None]
    report.check("runtime source mappings expose resolved provenance",
                 len(resolved) > 0, f"{len(resolved)} resolved")
    report.check("runtime provenance exposes page_or_section/scope_note",
                 any(p.page_or_section is not None for p in resolved)
                 and any(p.scope_note is not None for p in resolved),
                 "page_or_section/scope_note")

    # get_skill_evidence must return structured evidence with provenance for at
    # least one skill, and must never raise for any skill.
    sample_with_evidence = None
    for skill in skills:
        items = rs.get_skill_evidence(skill.skill_id)
        if any(item.granularity == "skill-level" and item.provenance is not None
               for item in items):
            sample_with_evidence = skill.skill_id
            break
    report.check("runtime skill evidence with provenance", sample_with_evidence is not None,
                 f"sample={sample_with_evidence}")


def _check_snapshot(report: Report) -> None:
    from app.evaluation.runner import compute_okb_snapshot
    from app.repositories.okb_repository import OKB_SNAPSHOT_COMPONENTS

    first = compute_okb_snapshot()
    second = compute_okb_snapshot()

    report.check("snapshot covers all components",
                 set(first.components) == set(OKB_SNAPSHOT_COMPONENTS),
                 f"got {sorted(first.components)}")
    expected_counts = {
        component: TABLE_COUNTS.get(component, None)
        for component in OKB_SNAPSHOT_COMPONENTS
    }
    mismatches = {
        component: (first.counts.get(component), expected)
        for component, expected in expected_counts.items()
        if expected is not None and first.counts.get(component) != expected
    }
    report.check("snapshot counts match DB", not mismatches, f"{mismatches}")
    report.check("snapshot counts non-zero",
                 all(value > 0 for value in first.counts.values()), f"{first.counts}")
    report.check("snapshot fingerprint is sha256",
                 len(first.fingerprint) == 64
                 and all(c in "0123456789abcdef" for c in first.fingerprint),
                 first.fingerprint)
    report.check("snapshot is deterministic", first.fingerprint == second.fingerprint,
                 "two consecutive calls differ")
    print("INFO  okb snapshot fingerprint: " + first.fingerprint)
    print("INFO  okb snapshot counts: " + str(first.counts))


def run_validation() -> None:
    engine = get_engine()
    report = Report()
    with engine.connect() as conn:
        _assert_safe_target(conn)
        print(f"INFO  validating database: {ALLOWED_E2E_DB}")

        sheets = _load_workbook(XLSX_PATH)
        try:
            _validate_workbook(sheets)
            report.check("workbook preflight", True)
        except WorkbookValidationError as exc:
            report.check("workbook preflight", False, str(exc))

        _check_counts(conn, report)
        _check_keys(conn, report)
        _check_foreign_keys(conn, report)
        _check_required(conn, report)
        _check_mapping_basis(conn, report)
        _check_content_parity(conn, sheets, report)
        _check_provenance_links(conn, report)

    _check_runtime_retrieval(report)
    _check_snapshot(report)
    report.finish()


def main() -> None:
    try:
        run_validation()
    except (ImportKBSafetyError, ValidationError) as exc:
        print(f"\nVALIDATION ABORTED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
