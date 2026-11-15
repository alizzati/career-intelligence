"""Unit tests for the attribution fields exposed by the retrieval schemas.

These guard against silently dropping source metadata between the database and
the runtime models consumed by the agents.
"""
from app.schemas.retrieval import (
    OccupationSourceMappingOut,
    ProvenanceOut,
    TaskOut,
    TechnologyOut,
)
from app.services.retrieval_service import _provenance_out


def test_task_out_exposes_source_metadata():
    task = TaskOut(
        task_id="TK001", task_description="d", task_category="CORE",
        importance=100, source="Kominfo_Kemnaker_BNSP",
        source_code="J.620100.001.1", source_period=2018, geography="Indonesia",
    )
    assert task.source_code == "J.620100.001.1"
    assert task.source_period == 2018
    assert task.geography == "Indonesia"


def test_technology_out_exposes_source_metadata():
    tech = TechnologyOut(
        technology_id="T001", technology_name="Python", technology_type="Language",
        frequency_pct=29, source="Lightcast", source_period=2025,
        geography="Indonesia", evidence_note="Employer-posting evidence.",
    )
    assert tech.source_period == 2025
    assert tech.geography == "Indonesia"
    assert tech.evidence_note


def test_source_mapping_out_exposes_title_and_scope():
    mapping = OccupationSourceMappingOut(
        mapping_id="OSM020", source_name="Kominfo_Kemnaker_BNSP",
        source_code="20708", source_title="SOFTWARE DEVELOPMENT EXPERT",
        source_scope="Indonesia", confidence="high", mapping_basis="derived-deterministic",
    )
    assert mapping.source_title == "SOFTWARE DEVELOPMENT EXPERT"
    assert mapping.source_scope == "Indonesia"


def test_provenance_out_exposes_page_and_scope():
    provenance = ProvenanceOut(
        provenance_id="P014", source_name="Kominfo_Kemnaker_BNSP_2018",
        document_id="Kominfo_Kemnaker_BNSP_2018", document_title="Daftar Unit",
        version_or_year="2018", page_or_section="occupation task & cannonical name",
        source_type="PPID Kemendagri", scope_note="Indonesia's occupation competency unit",
    )
    assert provenance.page_or_section
    assert provenance.scope_note


def test_provenance_out_from_repository_row_preserves_new_fields():
    row = {
        "p_id": "P014", "p_source_name": "Kominfo_Kemnaker_BNSP_2018",
        "document_id": "Kominfo_Kemnaker_BNSP_2018", "document_title": "Daftar Unit",
        "version_or_year": "2018", "page_or_section": "occupation task & cannonical name",
        "url": "https://example.test", "source_type": "PPID Kemendagri",
        "scope_note": "Indonesia's occupation competency unit",
    }
    provenance = _provenance_out(row)
    assert provenance is not None
    assert provenance.page_or_section == "occupation task & cannonical name"
    assert provenance.scope_note == "Indonesia's occupation competency unit"


def test_provenance_out_returns_none_without_resolved_record():
    assert _provenance_out({}) is None
    assert _provenance_out({"p_id": None}) is None
