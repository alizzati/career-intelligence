import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # make `app` importable
from sqlalchemy import text

from app.core.db import get_engine

BASE_DIR = Path(__file__).resolve().parents[2]
XLSX_PATH = BASE_DIR / "data" / "occupational_knowledge_base_verified_v1_0.xlsx"

ALLOWED_E2E_DB = "career_intelligence_e2e_test"
E2E_OPTIN_ENV = "CAREER_E2E_ISOLATED_DB_OK"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ImportKBSafetyError(RuntimeError):
    """Fail-closed safety violation for KB importer."""


def _validate_isolated_db_safety(engine) -> None:
    optin = os.environ.get(E2E_OPTIN_ENV, "")
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
        raise ImportKBSafetyError("KB import only allowed on career_intelligence_e2e_test database.")

    with engine.connect() as connection:
        current_db = connection.execute(text("SELECT current_database()")).scalar_one()
    if current_db != ALLOWED_E2E_DB:
        raise ImportKBSafetyError("KB import only allowed on career_intelligence_e2e_test database.")
    if current_db == "career_intelligence":
        raise ImportKBSafetyError("KB import must not run against production database career_intelligence.")


def _check_careers_empty(engine) -> None:
    with engine.connect() as connection:
        career_count = connection.execute(text("SELECT count(*) FROM careers")).scalar_one()
    if int(career_count) > 0:
        raise ImportKBSafetyError("KB import refused: careers table already contains data; append-only import is not permitted.")


def _run_import():
    engine = get_engine()
    _validate_isolated_db_safety(engine)
    _check_careers_empty(engine)

    xls = pd.ExcelFile(XLSX_PATH)

    def load(sheet):
        return pd.read_excel(xls, sheet)

    transform_log_rows = []

    def log_transform(table, pk, field, raw, transformed, ttype, note=None):
        transform_log_rows.append({
            "table_name": table, "record_pk": str(pk), "field_name": field,
            "raw_value": None if pd.isna(raw) else str(raw),
            "transformed_value": None if pd.isna(transformed) else str(transformed),
            "transform_type": ttype, "notes": note,
        })

    with engine.begin() as conn:
        # ---------- 1. skill_groups ----------
        sg = load("SKILL_GROUP")
        sg.to_sql("skill_groups", conn, if_exists="append", index=False)
        print(f"skill_groups: {len(sg)} rows")

        # ---------- 2. careers ----------
        career = load("CAREER")
        career.to_sql("careers", conn, if_exists="append", index=False)
        print(f"careers: {len(career)} rows")

        # ---------- 3. occupations ----------
        occupation = load("OCCUPATION")
        occupation.to_sql("occupations", conn, if_exists="append", index=False)
        print(f"occupations: {len(occupation)} rows")

        # ---------- 4. skills ----------
        skill = load("SKILL")
        skill.to_sql("skills", conn, if_exists="append", index=False)
        print(f"skills: {len(skill)} rows")

        # ---------- 5. career_occupations ----------
        co = load("CAREER_OCCUPATION")
        co.to_sql("career_occupations", conn, if_exists="append", index=False)
        print(f"career_occupations: {len(co)} rows")

        # ---------- 6. career_skills ----------
        cs = load("CAREER_SKILL").drop(columns=["skill_name"])
        cs.to_sql("career_skills", conn, if_exists="append", index=False)
        print(f"career_skills: {len(cs)} rows")

        # ---------- 7. skkni_standards (merge STANDARD_COVERAGE) ----------
        skkni = load("SKKNI_STANDARD")
        cov = load("STANDARD_COVERAGE").rename(columns={"action": "coverage_action_note"})
        skkni_merged = skkni.merge(
            cov[["standard_id", "unit_inventory_status", "unit_count_in_dataset",
                 "evidence_basis", "coverage_action_note"]],
            on="standard_id", how="left"
        )
        skkni_merged.to_sql("skkni_standards", conn, if_exists="append", index=False)
        print(f"skkni_standards: {len(skkni_merged)} rows")

        # ---------- 8. competency_units (Temuan A: padding normalization) ----------
        cu = load("COMPETENCY_UNIT").copy()
        cu["raw_unit_id"] = cu["unit_id"]

        def normalize_unit_id(uid):
            import re
            m = re.match(r"^(CU\d+_)(\d+)$", str(uid))
            if not m:
                return uid
            prefix, num = m.groups()
            return f"{prefix}{int(num):03d}"

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
        oc = load("OCCUPATION_COMPETENCY")
        oc.to_sql("occupation_competencies", conn, if_exists="append", index=False)
        print(f"occupation_competencies: {len(oc)} rows")

        # ---------- 10. competency_skills (apply unit_id normalization directly) ----------
        ck = load("COMPETENCY_SKILL").drop(columns=["skill_name"]).copy()
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
        tech = load("TECHNOLOGY")
        tech.to_sql("technologies", conn, if_exists="append", index=False)
        print(f"technologies: {len(tech)} rows")

        # ---------- 12. tasks ----------
        task = load("TASK")
        task.to_sql("tasks", conn, if_exists="append", index=False)
        print(f"tasks: {len(task)} rows")

        # ---------- 13. provenance ----------
        prov = load("PROVENANCE")
        prov.to_sql("provenance", conn, if_exists="append", index=False)
        print(f"provenance: {len(prov)} rows")

        # ---------- 14. occupation_source_mapping (provenance_id derivation) ----------
        osm = load("OCCUPATION_SOURCE_MAPPING").copy()
        prov_df = prov.copy()

        onet_prov = dict(zip(prov_df.loc[prov_df.source_name == "O*NET", "document_id"],
                              prov_df.loc[prov_df.source_name == "O*NET", "provenance_id"]))
        kbji_prov_id = prov_df.loc[prov_df.source_name.str.contains("KBJI", case=False, na=False), "provenance_id"]
        kbji_prov_id = kbji_prov_id.iloc[0] if len(kbji_prov_id) else None
        esco_prov_id = prov_df.loc[prov_df.source_name == "ESCO", "provenance_id"]
        esco_prov_id = esco_prov_id.iloc[0] if len(esco_prov_id) else None

        def derive_osm_provenance(row):
            if row["source_name"] == "O*NET":
                pid = onet_prov.get(row["source_code"])
                return pid, "derived-deterministic" if pid else "evidence-unavailable-ambiguous-source"
            if row["source_name"] == "KBJI":
                return kbji_prov_id, "derived-deterministic" if kbji_prov_id else "evidence-unavailable-ambiguous-source"
            if row["source_name"] == "ESCO":
                return esco_prov_id, "derived-deterministic" if esco_prov_id else "evidence-unavailable-ambiguous-source"
            if row["source_name"] == "IndoTask":
                return None, "evidence-unavailable-ambiguous-source"
            return None, "evidence-unavailable-ambiguous-source"

        osm[["provenance_id", "mapping_basis"]] = osm.apply(
            lambda r: pd.Series(derive_osm_provenance(r)), axis=1
        )
        for _, r in osm.iterrows():
            log_transform("occupation_source_mapping", r["mapping_id"], "provenance_id",
                          None, r["provenance_id"], "provenance_fk_derivation",
                          f"basis={r['mapping_basis']}, source={r['source_name']}")
        osm.to_sql("occupation_source_mapping", conn, if_exists="append", index=False)
        n_null = osm["provenance_id"].isna().sum()
        print(f"occupation_source_mapping: {len(osm)} rows ({n_null} left NULL - ambiguous IndoTask)")

        # ---------- 15. skill_source_evidence (provenance_id derivation) ----------
        sse = load("SKILL_SOURCE_EVIDENCE").drop(columns=["skill_name"]).copy()

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
            if row["source_name"] == "O*NET":
                pid = onet_prov.get(row["source_reference"])
                return pid, "derived-deterministic" if pid else "evidence-unavailable-ambiguous-source"
            if row["source_name"] == "SKKNI":
                ref = str(row["source_reference"])
                prefix = ".".join(ref.split(".")[:2])
                std_id = skkni_prefix_to_standard.get(prefix)
                pid = std_to_prov.get(std_id) if std_id else None
                return pid, "derived-deterministic" if pid else "evidence-unavailable-ambiguous-source"
            if row["source_name"] == "ESCO":
                return esco_prov_id, "derived-deterministic" if esco_prov_id else "evidence-unavailable-ambiguous-source"
            if row["source_name"] == "KBJI":
                return kbji_prov_id, "derived-deterministic" if kbji_prov_id else "evidence-unavailable-ambiguous-source"
            if row["source_name"] == "IndoTask":
                return None, "evidence-unavailable-ambiguous-source"
            return None, "evidence-unavailable-ambiguous-source"

        sse[["provenance_id", "mapping_basis"]] = sse.apply(
            lambda r: pd.Series(derive_sse_provenance(r)), axis=1
        )
        for _, r in sse.iterrows():
            log_transform("skill_source_evidence", r["evidence_id"], "provenance_id",
                          None, r["provenance_id"], "provenance_fk_derivation",
                          f"basis={r['mapping_basis']}, source={r['source_name']}")
        sse.to_sql("skill_source_evidence", conn, if_exists="append", index=False)
        n_null_sse = sse["provenance_id"].isna().sum()
        print(f"skill_source_evidence: {len(sse)} rows ({n_null_sse} left NULL)")

        # ---------- 16. etl_transform_log ----------
        log_columns = [
            "table_name",
            "record_pk",
            "field_name",
            "raw_value",
            "transformed_value",
            "transform_type",
            "notes",
        ]

        log_df = pd.DataFrame(transform_log_rows, columns=log_columns)
        log_df.to_sql("etl_transform_log", conn, if_exists="append", index=False)
        print(f"etl_transform_log: {len(log_df)} rows")

        print("\nETL COMPLETE.")


if __name__ == "__main__":
    _run_import()
