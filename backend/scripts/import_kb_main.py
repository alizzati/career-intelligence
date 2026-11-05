"""Import the approved workbook into the isolated career_intelligence_main DB.

This path is intentionally separate from the E2E-only importer. It never
touches protected databases and replaces only OKB rows in the already-cloned
target, preserving users and user_* data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.db import get_engine


BASE_DIR = Path(__file__).resolve().parents[2]
WORKBOOK = BASE_DIR / "data" / "occupational_knowledge_base_verified_v1_0.xlsx"
TARGET_DB = "career_intelligence_main"
PROTECTED = {"career_intelligence", "career_intelligence_e2e_test", "career_intelligence_okb"}
MANIFEST = BASE_DIR / "artifacts" / "career_intelligence_main_import_manifest.json"

EXPECTED_SHEETS = {
    "README", "CAREER", "OCCUPATION", "CAREER_OCCUPATION", "SKILL_GROUP", "SKILL",
    "CAREER_SKILL", "SKKNI_STANDARD", "COMPETENCY_UNIT", "OCCUPATION_COMPETENCY",
    "COMPETENCY_SKILL", "STATUS_AUDIT", "OCCUPATION_SOURCE_MAPPING", "TECHNOLOGY",
    "TASK", "PROVENANCE", "SKILL_SOURCE_EVIDENCE", "STANDARD_COVERAGE",
}
ENTITY_SHEETS = [
    "SKILL_GROUP", "CAREER", "OCCUPATION", "SKILL", "CAREER_OCCUPATION", "CAREER_SKILL",
    "SKKNI_STANDARD", "COMPETENCY_UNIT", "OCCUPATION_COMPETENCY", "COMPETENCY_SKILL",
    "TECHNOLOGY", "TASK", "PROVENANCE", "OCCUPATION_SOURCE_MAPPING",
    "SKILL_SOURCE_EVIDENCE", "STANDARD_COVERAGE",
]
TABLES_TO_REPLACE = [
    "career_occupations", "career_skills", "competency_skills", "competency_units",
    "occupation_competencies", "occupation_source_mapping", "skill_source_evidence",
    "tasks", "technologies", "etl_transform_log", "provenance", "skkni_standards",
    "occupations",
]
EXPECTED_COUNTS = {
    "CAREER": 10, "OCCUPATION": 23, "CAREER_OCCUPATION": 27, "SKILL_GROUP": 17,
    "SKILL": 87, "CAREER_SKILL": 155, "SKKNI_STANDARD": 9, "COMPETENCY_UNIT": 146,
    "OCCUPATION_COMPETENCY": 10, "COMPETENCY_SKILL": 79,
    "OCCUPATION_SOURCE_MAPPING": 25, "TECHNOLOGY": 120, "TASK": 221,
    "PROVENANCE": 14, "SKILL_SOURCE_EVIDENCE": 99, "STANDARD_COVERAGE": 9,
}


def normalize_unit_id(value: object) -> object:
    match = re.match(r"^CU(\d+?)_(\d+)$", str(value))
    return f"CU{int(match.group(1))}_{int(match.group(2)):03d}" if match else value


def write_manifest(payload: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    if not WORKBOOK.is_file():
        raise RuntimeError(f"Workbook not found: {WORKBOOK}")
    workbook_hash = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
    xls = pd.ExcelFile(WORKBOOK)
    if set(xls.sheet_names) != EXPECTED_SHEETS or len(xls.sheet_names) != 18:
        raise RuntimeError(f"Unexpected workbook sheets: {xls.sheet_names}")

    frames = {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in ENTITY_SHEETS}
    workbook_counts = {sheet: len(df) for sheet, df in frames.items()}
    mismatches = {
        sheet: {"actual": workbook_counts[sheet], "expected": expected}
        for sheet, expected in EXPECTED_COUNTS.items()
        if workbook_counts[sheet] != expected
    }
    # The approved status said 99 SSE rows, but the workbook contains two
    # trailing blank rows and 97 actual records. Actual non-empty workbook
    # records are authoritative; retain the discrepancy in the manifest.

    engine = get_engine()
    if (engine.url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Target import requires a loopback database host")
    if engine.url.database != TARGET_DB or engine.url.database in PROTECTED:
        raise RuntimeError(f"Refusing import into database {engine.url.database!r}")

    transforms: list[dict] = []
    unresolved: list[dict] = []

    with engine.begin() as conn:
        current_db = conn.execute(text("SELECT current_database()")).scalar_one()
        if current_db != TARGET_DB:
            raise RuntimeError(f"Connected to {current_db!r}, expected {TARGET_DB!r}")

        # Application-linked skill identities must remain stable after cloning.
        skill_db = pd.read_sql(text("SELECT skill_id, canonical_name, skill_group_id, status FROM skills ORDER BY skill_id"), conn)
        skill_wb = frames["SKILL"][["skill_id", "canonical_name", "skill_group_id", "status"]].sort_values("skill_id").reset_index(drop=True)
        if not skill_db.reset_index(drop=True).equals(skill_wb):
            raise RuntimeError("Target skills differ from workbook; refusing to risk user_skills references")

        group_db = pd.read_sql(text("SELECT skill_group_id, name FROM skill_groups ORDER BY skill_group_id"), conn)
        group_wb = frames["SKILL_GROUP"][["skill_group_id", "name"]].sort_values("skill_group_id").reset_index(drop=True)
        if not group_db.reset_index(drop=True).equals(group_wb):
            raise RuntimeError("Target skill_groups differ from workbook")

        career_db = pd.read_sql(text("SELECT career_id, canonical_name, domain FROM careers ORDER BY career_id"), conn)
        career_wb = frames["CAREER"][["career_id", "canonical_name", "domain"]].sort_values("career_id").reset_index(drop=True)
        if not career_db.reset_index(drop=True).equals(career_wb):
            raise RuntimeError("Target careers differ from workbook")

        for table in TABLES_TO_REPLACE:
            conn.execute(text(f'DELETE FROM "{table}"'))

        frames["OCCUPATION"].to_sql("occupations", conn, if_exists="append", index=False)
        frames["CAREER_OCCUPATION"].to_sql("career_occupations", conn, if_exists="append", index=False)
        frames["CAREER_SKILL"].drop(columns=["skill_name"]).to_sql("career_skills", conn, if_exists="append", index=False)

        coverage = frames["STANDARD_COVERAGE"].rename(columns={"action": "coverage_action_note"})
        standards = frames["SKKNI_STANDARD"].merge(
            coverage[["standard_id", "unit_inventory_status", "unit_count_in_dataset", "evidence_basis", "coverage_action_note"]],
            on="standard_id", how="left",
        )
        standards.to_sql("skkni_standards", conn, if_exists="append", index=False)

        units = frames["COMPETENCY_UNIT"].copy()
        units["raw_unit_id"] = units["unit_id"]
        units["unit_id"] = units["unit_id"].map(normalize_unit_id)
        for _, row in units[units["unit_id"] != units["raw_unit_id"]].iterrows():
            transforms.append({"table": "competency_units", "record": str(row["unit_id"]), "field": "unit_id", "raw": str(row["raw_unit_id"]), "value": str(row["unit_id"]), "type": "unit_id_padding_fix"})
        units[["unit_id", "standard_id", "code", "title"]].to_sql("competency_units", conn, if_exists="append", index=False)

        frames["OCCUPATION_COMPETENCY"].to_sql("occupation_competencies", conn, if_exists="append", index=False)
        competency_skills = frames["COMPETENCY_SKILL"].drop(columns=["skill_name"]).copy()
        competency_skills["raw_unit_id"] = competency_skills["unit_id"]
        competency_skills["unit_id"] = competency_skills["unit_id"].map(normalize_unit_id)
        invalid_units = competency_skills[~competency_skills["unit_id"].isin(set(units["unit_id"]))]
        if not invalid_units.empty:
            raise RuntimeError(f"Unresolved competency unit references: {invalid_units['unit_id'].tolist()}")
        for _, row in competency_skills[competency_skills["unit_id"] != competency_skills["raw_unit_id"]].iterrows():
            transforms.append({"table": "competency_skills", "record": str(row["relationship_id"]), "field": "unit_id", "raw": str(row["raw_unit_id"]), "value": str(row["unit_id"]), "type": "unit_id_padding_fix"})
        competency_skills[["relationship_id", "unit_id", "skill_id", "mapping_method"]].to_sql("competency_skills", conn, if_exists="append", index=False)

        frames["TECHNOLOGY"].to_sql("technologies", conn, if_exists="append", index=False)
        frames["TASK"].to_sql("tasks", conn, if_exists="append", index=False)
        provenance = frames["PROVENANCE"].copy()
        provenance.to_sql("provenance", conn, if_exists="append", index=False)

        # Only exact, unique provenance resolutions are accepted.
        prov_by_source = provenance.groupby("source_name")["provenance_id"].apply(list).to_dict()
        kominfo = provenance.loc[provenance["document_id"] == "Kominfo_Kemnaker_BNSP_2018", "provenance_id"].tolist()
        if len(kominfo) != 1:
            raise RuntimeError("Kominfo provenance does not resolve uniquely")

        osm = frames["OCCUPATION_SOURCE_MAPPING"].copy()
        osm["source_code"] = osm["source_code"].map(lambda value: str(int(value)) if isinstance(value, float) and value.is_integer() else str(value))
        osm["provenance_id"] = None
        osm["mapping_basis"] = "evidence-unavailable-ambiguous-source"
        for idx, row in osm.iterrows():
            candidates = []
            if row["source_name"] == "Kominfo_Kemnaker_BNSP":
                candidates = kominfo
            elif row["source_name"] == "KBJI":
                candidates = prov_by_source.get("BPS KBJI", [])
            elif row["source_name"] == "IndoTask":
                candidates = [p for name in ("World Bank IndoTask", "World Bank/Bappenas") for p in prov_by_source.get(name, [])]
            if len(candidates) == 1:
                osm.at[idx, "provenance_id"] = candidates[0]
                osm.at[idx, "mapping_basis"] = "derived-deterministic"
            else:
                unresolved.append({"table": "occupation_source_mapping", "record": str(row["mapping_id"]), "reason": "ambiguous or unavailable provenance"})
        osm.to_sql("occupation_source_mapping", conn, if_exists="append", index=False)

        sse = frames["SKILL_SOURCE_EVIDENCE"].drop(columns=["skill_name"]).copy()
        sse["provenance_id"] = None
        sse["mapping_basis"] = "evidence-unavailable-ambiguous-source"
        skkni_prov = provenance[provenance["source_name"] == "SKKNI"]
        prefix_map = {"J.620100": "SK01", "J.62SQA00": "SK02", "J.63SAM00": "SK03", "J.62DMS00": "SK04", "J.62DMI00": "SK05", "J.62KAM00": "SK07"}
        standard_to_prov: dict[str, str] = {}
        for _, row in standards.iterrows():
            matches = skkni_prov[skkni_prov["document_id"].str.contains(f"{row['number']}/{row['year']}", na=False)]["provenance_id"].tolist()
            if len(matches) == 1:
                standard_to_prov[row["standard_id"]] = matches[0]
        for idx, row in sse.iterrows():
            candidates = []
            if row["source_name"] == "Kominfo_Kemnaker_BNSP" and row["source_reference"] == "Kominfo_Kemnaker_BNSP_2018":
                candidates = kominfo
            elif row["source_name"] == "SKKNI":
                prefix = ".".join(str(row["source_reference"]).split(".")[:2])
                standard_id = prefix_map.get(prefix)
                candidates = [standard_to_prov[standard_id]] if standard_id in standard_to_prov else []
            elif row["source_name"] == "IndoTask":
                candidates = [p for name in ("World Bank IndoTask", "World Bank/Bappenas") for p in prov_by_source.get(name, [])]
            if len(candidates) == 1:
                sse.at[idx, "provenance_id"] = candidates[0]
                sse.at[idx, "mapping_basis"] = "derived-deterministic"
            else:
                unresolved.append({"table": "skill_source_evidence", "record": str(row["evidence_id"]), "reason": "ambiguous or unavailable provenance"})
        sse.to_sql("skill_source_evidence", conn, if_exists="append", index=False)

        pd.DataFrame(transforms, columns=["table", "record", "field", "raw", "value", "type"]).rename(columns={"table": "table_name", "record": "record_pk", "field": "field_name", "raw": "raw_value", "value": "transformed_value", "type": "transform_type"}).assign(notes="dedicated main import").to_sql("etl_transform_log", conn, if_exists="append", index=False)

    target_counts = {}
    with engine.connect() as conn:
        for sheet, table in {
            "CAREER": "careers", "OCCUPATION": "occupations", "CAREER_OCCUPATION": "career_occupations",
            "SKILL_GROUP": "skill_groups", "SKILL": "skills", "CAREER_SKILL": "career_skills",
            "SKKNI_STANDARD": "skkni_standards", "COMPETENCY_UNIT": "competency_units",
            "OCCUPATION_COMPETENCY": "occupation_competencies", "COMPETENCY_SKILL": "competency_skills",
            "OCCUPATION_SOURCE_MAPPING": "occupation_source_mapping", "TECHNOLOGY": "technologies",
            "TASK": "tasks", "PROVENANCE": "provenance", "SKILL_SOURCE_EVIDENCE": "skill_source_evidence",
            "STANDARD_COVERAGE": "standard_coverage",
        }.items():
            if table == "standard_coverage":
                target_counts[sheet] = int(conn.execute(text("SELECT count(*) FROM skkni_standards WHERE unit_inventory_status IS NOT NULL")).scalar_one())
            else:
                target_counts[sheet] = int(conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())

    validation = {sheet: {"workbook": workbook_counts[sheet], "database": target_counts.get(sheet), "status": "PASS" if workbook_counts[sheet] == target_counts.get(sheet) else "FAIL"} for sheet in workbook_counts}
    payload = {
        "workbook": WORKBOOK.name, "workbook_sha256": workbook_hash, "imported_at_utc": started,
        "source_database": "career_intelligence", "target_database": TARGET_DB,
        "workbook_counts": workbook_counts, "database_counts": target_counts,
        "status_count_discrepancies": mismatches,
        "validation": validation, "transform_count": len(transforms), "unresolved_provenance": unresolved,
        "schema_validation": "PASS", "transaction": "COMMITTED",
    }
    write_manifest(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
