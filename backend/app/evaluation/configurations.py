"""The four agreed experimental configurations.

These definitions are descriptive metadata only. Step 17 does not implement
runtime switching, ablation execution, or a baseline runner; that belongs to
Step 18. The values mirror ``docs/evaluation/EVALUATION_PROTOCOL.md`` section 4
and ``docs/evaluation/EXPERIMENT_SPEC.md`` section 2 exactly.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.evaluation.schemas import ConfigId


class ConfigurationDefinition(BaseModel):
    config_id: ConfigId
    label: str
    uses_occupational_kb: bool
    uses_deterministic_matching: bool
    uses_verification_agent: bool
    uses_revision_loop: bool
    llm_decides_ranking: bool
    llm_decides_skill_gap: bool
    description: str


CONFIGURATION_DEFINITIONS: dict[ConfigId, ConfigurationDefinition] = {
    "B0": ConfigurationDefinition(
        config_id="B0",
        label="LLM-only baseline",
        uses_occupational_kb=False,
        uses_deterministic_matching=False,
        uses_verification_agent=False,
        uses_revision_loop=False,
        llm_decides_ranking=True,
        llm_decides_skill_gap=True,
        description=(
            "LLM-only baseline with no Occupational Knowledge Base access, no "
            "deterministic matching/scoring, and no Verification Agent."
        ),
    ),
    "B2": ConfigurationDefinition(
        config_id="B2",
        label="LLM with OKB relations",
        uses_occupational_kb=True,
        uses_deterministic_matching=False,
        uses_verification_agent=False,
        uses_revision_loop=False,
        llm_decides_ranking=True,
        llm_decides_skill_gap=True,
        description=(
            "The LLM receives the occupational relationship data and canonical "
            "career/skill space, but performs matching, ranking, and gap "
            "classification itself; no deterministic engine and no verifier."
        ),
    ),
    "B3": ConfigurationDefinition(
        config_id="B3",
        label="System pipeline without verification",
        uses_occupational_kb=True,
        uses_deterministic_matching=True,
        uses_verification_agent=False,
        uses_revision_loop=False,
        llm_decides_ranking=False,
        llm_decides_skill_gap=False,
        description=(
            "Deterministic system pipeline (retrieval, compute_career_fit, "
            "classify_skill_gap, roadmap) with the Verification Agent and "
            "revision loop omitted."
        ),
    ),
    "F": ConfigurationDefinition(
        config_id="F",
        label="Full hybrid verified multi-agent system",
        uses_occupational_kb=True,
        uses_deterministic_matching=True,
        uses_verification_agent=True,
        uses_revision_loop=True,
        llm_decides_ranking=False,
        llm_decides_skill_gap=False,
        description=(
            "The complete architecture: OKB access, deterministic career-fit "
            "and skill-gap engines, recommendation/roadmap generation, the "
            "Verification Agent, and the bounded revision loop."
        ),
    ),
}


def get_configuration(config_id: str) -> ConfigurationDefinition:
    """Return the definition for one of the four agreed configuration IDs."""
    try:
        return CONFIGURATION_DEFINITIONS[config_id]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(
            f"unknown configuration {config_id!r}; expected one of "
            f"{sorted(CONFIGURATION_DEFINITIONS)}"
        ) from exc


def validate_configuration_manifest(manifest: dict) -> ConfigurationDefinition:
    """Validate a Step 18 run manifest describes an agreed configuration.

    Only the configuration declaration is checked here. The manifest may carry
    additional reproducibility fields; they are ignored rather than interpreted.
    """
    if not isinstance(manifest, dict):
        raise ValueError("configuration manifest must be a mapping")
    config_id = manifest.get("config_id")
    if not isinstance(config_id, str):
        raise ValueError("configuration manifest must declare a string config_id")
    return get_configuration(config_id)
