"""Typed input, prediction, and output contracts for Step 17 evaluation.

Design rules:

* A *prediction* is what a system configuration produced. Predictions are
  optional because a failed run may have no usable output; they are never
  invented by this package.
* A *reference* is an independently supplied label set. References are optional
  for the same reason: when they are absent the affected metric is reported as
  ``unavailable`` instead of being guessed.
* All models are strict about corrupted inputs (duplicate IDs, negative
  relevance, inconsistent fault labels) so a malformed annotation file fails
  loudly rather than silently changing a metric.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ConfigId = Literal["B0", "B2", "B3", "F"]
DatasetType = Literal["R", "S-H", "S-M"]
SplitName = Literal["train", "dev", "test", "pilot", "formal"]
RunStatus = Literal["completed", "failed"]
VerificationStatus = Literal["PASS", "FAIL", "REVISE", "unavailable"]

# The three statuses a *required* career skill can have. The fourth canonical
# category, unmatched_user_claims, labels user claims rather than required
# skills and is therefore represented by its own key list, never folded into
# the required-skill status map.
RequiredSkillStatus = Literal["matched_evidenced", "matched_claimed_only", "missing"]


class _NonEmptyIds(BaseModel):
    """Shared validation for lists that identify records."""

    @staticmethod
    def _unique(values: list[str], field_name: str) -> list[str]:
        cleaned = [value for value in values]
        if any(not isinstance(value, str) or not value.strip() for value in cleaned):
            raise ValueError(f"{field_name} must contain non-empty strings")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError(f"{field_name} must not contain duplicate IDs")
        return cleaned


class CareerRelevanceLabel(BaseModel):
    """Relevance of one canonical career for one profile.

    ``relevance`` is binary (0/1) or graded. Graded labels are supported by
    nDCG; Hit@k treats any value >= 1 as relevant. Negative values are invalid.
    """

    career_id: str
    relevance: float = Field(ge=0)

    @field_validator("career_id")
    @classmethod
    def _career_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("career_id must be a non-empty string")
        return value


class RecommendationReference(BaseModel):
    """Human/annotation reference for the profile-level ranking task."""

    profile_id: str
    labels: list[CareerRelevanceLabel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_labels(self) -> "RecommendationReference":
        ids = [label.career_id for label in self.labels]
        if len(set(ids)) != len(ids):
            raise ValueError("recommendation labels must not repeat a career_id")
        return self


class SkillStatusLabel(BaseModel):
    """Reference status for one required skill of a career."""

    skill_id: str
    status: RequiredSkillStatus

    @field_validator("skill_id")
    @classmethod
    def _skill_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("skill_id must be a non-empty string")
        return value


class SkillGapReference(BaseModel):
    """Reference labels for a single career's deterministic gap result.

    ``unmatched_user_claim_keys`` holds opaque, harness-chosen identifiers for
    user claims that have no canonical mapping. They are evaluated as a set and
    are never reinterpreted as missing required skills.
    """

    profile_id: str
    career_id: str
    required_skill_status: list[SkillStatusLabel] = Field(default_factory=list)
    unmatched_user_claim_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_skills(self) -> "SkillGapReference":
        ids = [label.skill_id for label in self.required_skill_status]
        if len(set(ids)) != len(ids):
            raise ValueError("required_skill_status must not repeat a skill_id")
        if len(set(self.unmatched_user_claim_keys)) != len(self.unmatched_user_claim_keys):
            raise ValueError("unmatched_user_claim_keys must not repeat a key")
        return self


class KbReference(BaseModel):
    """Canonical knowledge-base facts used for lineage checks.

    Only identifiers already present in the Occupational Knowledge Base belong
    here. This model never creates or infers KB content.
    """

    canonical_career_ids: list[str] = Field(default_factory=list)
    required_skill_ids_by_career: dict[str, list[str]] = Field(default_factory=dict)
    known_skill_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "KbReference":
        _NonEmptyIds._unique(self.canonical_career_ids, "canonical_career_ids")
        _NonEmptyIds._unique(self.known_skill_ids, "known_skill_ids")
        unknown_careers = set(self.required_skill_ids_by_career) - set(self.canonical_career_ids)
        if unknown_careers:
            raise ValueError(
                "required_skill_ids_by_career contains careers outside canonical_career_ids: "
                + ", ".join(sorted(unknown_careers))
            )
        for career_id, skill_ids in self.required_skill_ids_by_career.items():
            _NonEmptyIds._unique(skill_ids, f"required_skill_ids_by_career[{career_id}]")
        return self


class VerificationReference(BaseModel):
    """Labels from a controlled fault-injection run.

    ``injected_fault_ids`` identifies the claims that are known to be unsupported
    (true positives to detect). ``audited_claim_ids`` is the full claim universe
    for the run; it is used as the negative pool for the false-positive rate. If
    it is omitted, the false-positive rate is reported as unavailable rather than
    assuming every unreported claim was clean.
    """

    profile_id: str
    injected_fault_ids: list[str] = Field(default_factory=list)
    audited_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "VerificationReference":
        _NonEmptyIds._unique(self.injected_fault_ids, "injected_fault_ids")
        _NonEmptyIds._unique(self.audited_claim_ids, "audited_claim_ids")
        if self.audited_claim_ids:
            missing = set(self.injected_fault_ids) - set(self.audited_claim_ids)
            if missing:
                raise ValueError(
                    "injected_fault_ids must be a subset of audited_claim_ids: "
                    + ", ".join(sorted(missing))
                )
        return self


class EvaluationReferences(BaseModel):
    """All independently supplied labels for one profile/configuration run."""

    recommendation: RecommendationReference | None = None
    skill_gap: SkillGapReference | None = None
    verification: VerificationReference | None = None
    kb: KbReference | None = None

    @model_validator(mode="after")
    def _profile_ids_agree(self) -> "EvaluationReferences":
        declared = {
            value.profile_id
            for value in (self.recommendation, self.skill_gap, self.verification)
            if value is not None
        }
        if len(declared) > 1:
            raise ValueError("reference sections must refer to the same profile_id")
        return self


class RecommendationPrediction(BaseModel):
    """Ranked career IDs (rank 1 first) plus the IDs used for lineage checks."""

    ranking: list[str] = Field(default_factory=list)
    fit_scores: dict[str, float] = Field(default_factory=dict)
    referenced_skill_ids: dict[str, list[str]] = Field(default_factory=dict)
    evidenced_skill_ids: dict[str, list[str]] = Field(default_factory=dict)
    evidence_reference_counts: dict[str, dict[str, int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _valid(self) -> "RecommendationPrediction":
        _NonEmptyIds._unique(self.ranking, "ranking")
        for career_id, ids in self.referenced_skill_ids.items():
            _NonEmptyIds._unique(ids, f"referenced_skill_ids[{career_id}]")
        for career_id, ids in self.evidenced_skill_ids.items():
            _NonEmptyIds._unique(ids, f"evidenced_skill_ids[{career_id}]")
        for career_id, counts in self.evidence_reference_counts.items():
            for skill_id, count in counts.items():
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    raise ValueError(
                        f"evidence_reference_counts[{career_id}][{skill_id}] must be a "
                        "non-negative integer"
                    )
        return self


class SkillGapPrediction(BaseModel):
    """Predicted status for each required skill of one career."""

    career_id: str
    required_skill_status: dict[str, RequiredSkillStatus] = Field(default_factory=dict)
    unmatched_user_claim_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid(self) -> "SkillGapPrediction":
        if not self.career_id.strip():
            raise ValueError("career_id must be a non-empty string")
        if len(set(self.unmatched_user_claim_keys)) != len(self.unmatched_user_claim_keys):
            raise ValueError("unmatched_user_claim_keys must not repeat a key")
        return self


class RoadmapItemPrediction(BaseModel):
    """One generated learning-focus item."""

    skill_id: str
    gap_status: Literal["matched_claimed_only", "missing"]
    learning_action: Literal["develop_skill", "add_linked_evidence"]
    knowledge_base_basis: str = ""


class RoadmapPrediction(BaseModel):
    items: list[RoadmapItemPrediction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_items(self) -> "RoadmapPrediction":
        ids = [item.skill_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("roadmap items must not repeat a skill_id")
        return self


class VerificationCheckPrediction(BaseModel):
    check: str
    status: Literal["PASS", "FAIL", "REVISE"]


class VerificationPrediction(BaseModel):
    """Verification outcome and the claim identifiers it reported.

    ``reported_claim_ids`` must use the same opaque key convention as
    ``VerificationReference``. For real workflow output the adapter in
    ``adapters.py`` derives keys from ``component`` and ``claim`` text; a Step 18
    harness may inject a different key function when it owns the fault labels.
    """

    status: VerificationStatus = "unavailable"
    checks: list[VerificationCheckPrediction] = Field(default_factory=list)
    reported_claim_ids: list[str] = Field(default_factory=list)
    first_pass_status: VerificationStatus | None = None
    revision_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _unique_claims(self) -> "VerificationPrediction":
        if len(set(self.reported_claim_ids)) != len(self.reported_claim_ids):
            raise ValueError("reported_claim_ids must not repeat a key")
        return self


class OperationalMetadata(BaseModel):
    """Safe runtime metadata. Free text and prompts are deliberately excluded."""

    latency_ms: float | None = Field(default=None, ge=0)
    token_usage: int | None = Field(default=None, ge=0)
    api_call_count: int | None = Field(default=None, ge=0)
    retry_count: int | None = Field(default=None, ge=0)
    revision_count: int | None = Field(default=None, ge=0)


class EvaluationCase(BaseModel):
    """One profile evaluated under one experimental configuration."""

    profile_id: str
    config_id: ConfigId
    dataset_type: DatasetType | None = None
    split: SplitName | None = None
    run_status: RunStatus = "completed"
    references: EvaluationReferences | None = None
    recommendation: RecommendationPrediction | None = None
    skill_gap: SkillGapPrediction | None = None
    roadmap: RoadmapPrediction | None = None
    verification: VerificationPrediction | None = None
    operational: OperationalMetadata | None = None

    @field_validator("profile_id")
    @classmethod
    def _profile_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("profile_id must be a non-empty string")
        return value


class MetricResult(BaseModel):
    """One machine-readable metric value.

    ``status`` distinguishes a genuine zero from an undefined or unavailable
    measurement. ``n`` is the number of profiles that contributed; ``skipped``
    counts profiles where the metric applied but could not be computed, so a
    reader can see coverage instead of assuming the denominator is the full run.
    """

    name: str
    status: Literal["computed", "unavailable"]
    value: float | None = None
    unit: Literal["ratio", "score", "count", "ms", "tokens", "calls"] = "ratio"
    n: int = 0
    skipped: int = 0
    reason: str | None = None

    @model_validator(mode="after")
    def _value_matches_status(self) -> "MetricResult":
        if self.status == "computed" and self.value is None:
            raise ValueError("a computed metric must have a numeric value")
        if self.status == "unavailable" and self.value is not None:
            raise ValueError("an unavailable metric must not carry a value")
        return self


class ProfileEvaluation(BaseModel):
    profile_id: str
    config_id: ConfigId
    metrics: dict[str, MetricResult] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Aggregated, JSON-serializable evaluation output for one configuration."""

    schema_version: Literal["evaluation/1.0"] = "evaluation/1.0"
    generated_at: str
    config_id: ConfigId
    case_count: int
    profile_count: int
    failed_case_count: int
    metrics: dict[str, MetricResult] = Field(default_factory=dict)
    profiles: list[ProfileEvaluation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (Pydantic handles nested models)."""
        return self.model_dump(mode="json")
