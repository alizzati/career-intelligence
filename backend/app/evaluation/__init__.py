"""Step 17 evaluation framework.

This package implements the executable measurement layer that supports the
research questions in ``MASTER_SPEC`` sections 20, 21, and 25 and the metric
definitions in ``docs/evaluation``. It does not implement Step 18 baseline /
ablation runners, does not change any agent, deterministic engine, KB record,
API contract, or Step 16 log record, and never fabricates reference labels.
"""
from app.evaluation.configurations import (
    CONFIGURATION_DEFINITIONS,
    get_configuration,
    validate_configuration_manifest,
)
from app.evaluation.adapters import (
    case_from_analysis_record,
    recommendation_prediction_from_outputs,
    roadmap_prediction_from_outputs,
    skill_gap_prediction_from_outputs,
    verification_prediction_from_outputs,
)
from app.evaluation.evaluator import (
    PROFILE_EVALUATION_SCHEMA_VERSION,
    evaluate_case,
    evaluate_report,
)
from app.evaluation.schemas import (
    CareerRelevanceLabel,
    EvaluationCase,
    EvaluationReferences,
    EvaluationReport,
    KbReference,
    MetricResult,
    OperationalMetadata,
    ProfileEvaluation,
    RecommendationPrediction,
    RecommendationReference,
    RoadmapItemPrediction,
    RoadmapPrediction,
    SkillGapPrediction,
    SkillGapReference,
    SkillStatusLabel,
    VerificationCheckPrediction,
    VerificationPrediction,
    VerificationReference,
)

__all__ = [
    "CONFIGURATION_DEFINITIONS",
    "PROFILE_EVALUATION_SCHEMA_VERSION",
    "CareerRelevanceLabel",
    "EvaluationCase",
    "EvaluationReferences",
    "EvaluationReport",
    "KbReference",
    "MetricResult",
    "OperationalMetadata",
    "ProfileEvaluation",
    "RecommendationPrediction",
    "RecommendationReference",
    "RoadmapItemPrediction",
    "RoadmapPrediction",
    "SkillGapPrediction",
    "SkillGapReference",
    "SkillStatusLabel",
    "VerificationCheckPrediction",
    "VerificationPrediction",
    "VerificationReference",
    "case_from_analysis_record",
    "evaluate_case",
    "evaluate_report",
    "get_configuration",
    "recommendation_prediction_from_outputs",
    "roadmap_prediction_from_outputs",
    "skill_gap_prediction_from_outputs",
    "validate_configuration_manifest",
    "verification_prediction_from_outputs",
]
