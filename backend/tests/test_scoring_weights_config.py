"""Step 14.1: the YAML is really loaded (not silently replaced by inline defaults)."""
import os
from pathlib import Path

import yaml          # deliberately a hard import: a missing PyYAML must fail, not skip

from app.services import career_fit_service as cfs

BACKEND = Path(__file__).resolve().parents[1]
CONFIG = BACKEND / "config" / "scoring_weights.yaml"
EXPECTED = {
    "core_weight": 1.0, "supporting_weight": 0.5, "claim_only_multiplier": 0.5,
    "confidence_multiplier": {"high": 1.0, "medium": 0.85, "low": 0.7},
    "proficiency_modifier": 0.1,
}


def test_loader_default_path_exists_and_misspelled_file_is_gone():
    computed = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(cfs.__file__))))) \
        / "config" / "scoring_weights.yaml"
    assert computed.is_file()
    assert not (BACKEND / "config" / "scoring_weight.yaml").exists()


def test_configured_values_are_loaded_not_the_inline_defaults(monkeypatch):
    sentinel = {"core_weight": 99.0, "supporting_weight": 99.0, "claim_only_multiplier": 99.0,
                "confidence_multiplier": {"high": 99.0}, "proficiency_modifier": 99.0}
    monkeypatch.setattr(cfs, "DEFAULT_WEIGHTS", sentinel)      # a fallback would now be visible
    loaded = cfs.load_scoring_weights()
    assert loaded == EXPECTED
    assert loaded == yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_yaml_and_inline_defaults_stay_in_sync():
    assert cfs.load_scoring_weights() == cfs.DEFAULT_WEIGHTS


def test_custom_config_path_overrides_defaults_and_missing_path_falls_back(tmp_path):
    custom = tmp_path / "w.yaml"
    custom.write_text("core_weight: 2.0\nclaim_only_multiplier: 0.25\n", encoding="utf-8")
    loaded = cfs.load_scoring_weights(str(custom))
    assert loaded["core_weight"] == 2.0 and loaded["claim_only_multiplier"] == 0.25
    assert loaded["supporting_weight"] == cfs.DEFAULT_WEIGHTS["supporting_weight"]
    assert cfs.load_scoring_weights(str(tmp_path / "absent.yaml")) == cfs.DEFAULT_WEIGHTS