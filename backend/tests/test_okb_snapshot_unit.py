"""Unit tests for the expanded OKB snapshot.

The snapshot is exercised with a monkeypatched row loader so the tests stay
offline and deterministic while still asserting full component coverage and
change sensitivity.
"""
from app.evaluation import runner
from app.repositories.okb_repository import OKB_SNAPSHOT_COMPONENTS


def _empty_rows():
    return {name: [] for name in OKB_SNAPSHOT_COMPONENTS}


def test_snapshot_covers_every_okb_component(monkeypatch):
    rows = {name: [{"row": name}] for name in OKB_SNAPSHOT_COMPONENTS}
    monkeypatch.setattr(runner, "_load_okb_snapshot_rows", lambda: rows)

    snapshot = runner.compute_okb_snapshot()

    assert set(snapshot.components) == set(OKB_SNAPSHOT_COMPONENTS)
    assert snapshot.counts == {name: 1 for name in OKB_SNAPSHOT_COMPONENTS}
    assert {
        "occupations", "career_occupations", "tasks", "technologies",
        "provenance", "occupation_source_mapping", "skill_source_evidence",
        "competency_units", "competency_skills", "occupation_competencies",
    }.issubset(snapshot.components)
    assert len(snapshot.fingerprint) == 64


def test_snapshot_changes_when_any_component_changes(monkeypatch):
    rows = _empty_rows()
    monkeypatch.setattr(runner, "_load_okb_snapshot_rows", lambda: rows)

    baseline = runner.compute_okb_snapshot().fingerprint

    rows["tasks"] = [{"task_id": "TK001", "task_description": "x"}]
    after_task = runner.compute_okb_snapshot().fingerprint
    assert after_task != baseline

    rows["occupation_source_mapping"] = [{"mapping_id": "OSM001"}]
    after_mapping = runner.compute_okb_snapshot().fingerprint
    assert after_mapping != after_task

    rows["provenance"] = [{"provenance_id": "P001"}]
    after_provenance = runner.compute_okb_snapshot().fingerprint
    assert after_provenance != after_mapping


def test_snapshot_is_deterministic_for_identical_rows(monkeypatch):
    rows = {name: [{"row": name}] for name in OKB_SNAPSHOT_COMPONENTS}
    monkeypatch.setattr(runner, "_load_okb_snapshot_rows", lambda: rows)

    assert runner.compute_okb_snapshot().fingerprint == runner.compute_okb_snapshot().fingerprint
