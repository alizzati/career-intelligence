"""Step 13: stateful orchestration for the existing career agents."""
import logging
import os
import re
from typing import Callable, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.learning_roadmap_agent import LearningRoadmapAgent
from app.agents.llm_client import LLMClient
from app.agents.profile_agent import ProfileAgent, ProfileAgentResult
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.verification_agent import VerificationAgent
from app.schemas.career_fit import CareerRecommendationOut
from app.schemas.learning_roadmap import LearningRoadmapOut
from app.schemas.skill_gap_agent import SkillGapAnalysisOut
from app.schemas.user import UserFullProfileOut
from app.schemas.verification import VerificationResult
from app.services.pii_redaction_service import redact_pii
from app.services.profile_privacy_service import (
    redact_recommendations, redact_roadmap, redact_skill_gap_analysis,
)
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.services.evidence_acceptance_service import EvidenceGate
from app.evaluation.configurations import get_configuration
from app.evaluation.baseline_inference import (
    BaselineInferenceAgent, BaselineInferenceResult, CareerOutputLabel, FrozenProfileBundle,
    FrozenProfileBundleExtractor,
)

logger = logging.getLogger(__name__)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _safe_log_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.]", "_", value)[:160]


def _log_workflow_failure(stage: str, exc: Exception) -> None:
    diagnostics_enabled = (
        os.environ.get("CAREER_API_DIAGNOSTIC_LOGGING", "").strip().lower()
        in _TRUE_VALUES
    )
    remote_clients_enabled = (
        os.environ.get("CAREER_API_ALLOW_REMOTE_CLIENTS", "").strip().lower()
        in _TRUE_VALUES
    )
    if not diagnostics_enabled or remote_clients_enabled:
        return

    exception_type = type(exc)
    provider_code = getattr(exc, "code", None)
    provider_status = getattr(exc, "status_code", None)
    if type(provider_code) is not int:
        provider_code = None
    if type(provider_status) is not int:
        provider_status = None

    frames = []
    traceback = exc.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        filename = os.path.basename(frame.f_code.co_filename)
        function = frame.f_code.co_name
        location = (
            f"{_safe_log_component(filename)}:"
            f"{_safe_log_component(function)}:{traceback.tb_lineno}"
        )
        frames.append(location)
        traceback = traceback.tb_next
    frame_locations = ",".join(frames[-12:]) or "unavailable"

    logger.error(
        "Workflow stage failed: stage=%s exception=%s.%s "
        "provider_code=%s provider_status=%s frames=%s",
        _safe_log_component(stage),
        _safe_log_component(exception_type.__module__),
        _safe_log_component(exception_type.__name__),
        provider_code if provider_code is not None else "unavailable",
        provider_status if provider_status is not None else "unavailable",
        frame_locations,
    )


WorkflowFinalStatus = Literal[
    "RUNNING",
    "VERIFIED",
    "VERIFICATION_FAILED",
    "REVISION_LIMIT_REACHED",
    "UNVERIFIED",
    "ERROR",
]
RevisionTarget = Literal["evidence", "career_recommendation", "skill_gap", "roadmap"]


class WorkflowError(TypedDict):
    stage: str
    error_type: str
    message: str


class CareerWorkflowState(TypedDict):
    """Minimum state needed to coordinate the existing agent contracts."""

    user_id: int
    configuration_id: NotRequired[str]
    first_pass_verification_status: NotRequired[str | None]
    target_career_id: str | None
    redacted_profile_text: NotRequired[str]
    profile_result: NotRequired[ProfileAgentResult | UserFullProfileOut | None]
    recommendations: NotRequired[list[CareerRecommendationOut] | None]
    skill_gap: NotRequired[SkillGapAnalysisOut | None]
    roadmap: NotRequired[LearningRoadmapOut | None]
    verification: NotRequired[VerificationResult | None]
    stage: str
    revision_count: int
    revision_target: NotRequired[RevisionTarget | None]
    final_status: WorkflowFinalStatus
    errors: list[WorkflowError]
    baseline_result: NotRequired[BaselineInferenceResult | None]
    input_profile_bundle: NotRequired[FrozenProfileBundle | None]


class CareerWorkflow:
    """Compiled LangGraph workflow; agent implementations remain injected/reused.

    Existing agent interfaces have no feedback-taking revision methods. When a
    verifier finding identifies an owner, orchestration reruns that existing
    agent, then reruns dependent downstream stages before verification.
    """

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        max_revisions: int = 2,
        profile_agent: ProfileAgent | None = None,
        career_recommendation_agent: CareerRecommendationAgent | None = None,
        skill_gap_agent: SkillGapAgent | None = None,
        learning_roadmap_agent: LearningRoadmapAgent | None = None,
        verification_agent: VerificationAgent | None = None,
        evidence_gate: EvidenceGate | None = None,
        configuration_id: str = "F",
        career_labels: list[CareerOutputLabel] | None = None,
    ):
        if not isinstance(max_revisions, int) or isinstance(max_revisions, bool) or max_revisions < 0:
            raise ValueError("max_revisions must be a non-negative integer")
        self.max_revisions = max_revisions
        self.llm_client = llm_client
        self.configuration = get_configuration(configuration_id)
        self.career_labels = career_labels
        self.baseline_agent = (
            BaselineInferenceAgent(llm_client=llm_client, configuration_id=configuration_id)
            if configuration_id in {"B0", "B2"} and llm_client is not None else None
        )
        if configuration_id in {"B0", "B2"} and llm_client is None:
            raise ValueError(f"{configuration_id} requires the configured LLM client")
        self.profile_agent = (
            profile_agent
            if profile_agent is not None
            else ProfileAgent(llm_client) if llm_client is not None else None
        )
        self.career_recommendation_agent = (
            career_recommendation_agent
            if career_recommendation_agent is not None
            else CareerRecommendationAgent(llm_client=llm_client)
        )
        self.skill_gap_agent = (
            skill_gap_agent
            if skill_gap_agent is not None
            else SkillGapAgent(llm_client=llm_client)
        )
        self.learning_roadmap_agent = (
            learning_roadmap_agent
            if learning_roadmap_agent is not None
            else LearningRoadmapAgent(llm_client=llm_client)
        )
        self.verification_agent = (
            verification_agent
            if verification_agent is not None
            else VerificationAgent(llm_client=llm_client)
        )
        self.evidence_gate = (
            evidence_gate if evidence_gate is not None else EvidenceGate(llm_client=llm_client)
        )
        self.graph = None if configuration_id in {"B0", "B2"} else self._compile()

    @staticmethod
    def _error_update(
        stage: str,
        exc: Exception,
        *,
        safe_message: str | None = None,
    ) -> dict:
        _log_workflow_failure(stage, exc)
        return {
            "stage": stage,
            "final_status": "ERROR",
            "errors": [{
                "stage": stage,
                "error_type": type(exc).__name__,
                "message": safe_message or str(exc)[:500] or type(exc).__name__,
            }],
        }

    @staticmethod
    def _stage_error_update(
        stage: str,
        exc: Exception,
        state: CareerWorkflowState,
    ) -> dict:
        safe_message = None
        if state.get("redacted_profile_text") is not None:
            safe_message = f"{stage} failed; submitted profile details were omitted."
        return CareerWorkflow._error_update(stage, exc, safe_message=safe_message)

    def _profile_analysis(self, state: CareerWorkflowState) -> dict:
        try:
            frozen_bundle = state.get("input_profile_bundle")
            if frozen_bundle is not None:
                if self.profile_agent is None:
                    raise RuntimeError("a ProfileAgent is required to normalize the frozen profile bundle")
                result = self.profile_agent.run_from_bundle(state["user_id"], frozen_bundle)
                return self._profile_result_update(state, result)
            profile_text = state.get("redacted_profile_text")
            if profile_text is not None:
                if not profile_text.strip():
                    raise ValueError("raw_profile_text must not be empty when supplied")
                if self.profile_agent is None:
                    raise RuntimeError(
                        "raw_profile_text requires a ProfileAgent configured with an LLMClient"
                    )
                result = self.profile_agent.run(state["user_id"], profile_text)
            else:
                # Existing user profiles are already parsed/persisted; do not
                # run profile extraction a second time.
                result = us.get_user_full_profile(state["user_id"])
                if result is None:
                    raise ValueError(f"user_id={state['user_id']} does not exist")
            return self._profile_result_update(state, result)
        except Exception as exc:
            return self._error_update(
                "profile_analysis",
                exc,
                safe_message="Profile analysis failed; submitted profile details were omitted.",
            )

    def _profile_result_update(self, state: CareerWorkflowState, result) -> dict:
        """Route initial REVISE candidates through the existing bounded gate."""
        revise_count = int(getattr(result, "evidence_revise", 0) or 0)
        revision_count = state["revision_count"]
        revision_target = state.get("revision_target")
        if revise_count:
            if self.configuration.uses_revision_loop and revision_count < self.max_revisions:
                revision_count += 1
                revision_target = "evidence"
            else:
                # B0/B2/B3 have no revision loop, and F may have a zero
                # revision budget. Do not retain raw CV spans when no recheck
                # can occur; the candidate remains visibly REVISE/non-accepted.
                self.evidence_gate.discard_revise_spans(state["user_id"])
        return {
            "profile_result": result,
            "revision_count": revision_count,
            "revision_target": revision_target,
            "stage": "profile_analysis",
            "final_status": "RUNNING",
        }

    @staticmethod
    def _after_profile(state: CareerWorkflowState) -> str:
        if state["final_status"] == "ERROR":
            return "final_result"
        return "evidence_gate" if state.get("revision_target") == "evidence" else "career_recommendation"

    def _evidence_gate(self, state: CareerWorkflowState) -> dict:
        """Reassess REVISE evidence, then regenerate downstream outputs.

        The Evidence Gate owns evidence acceptance; it never rewrites the
        verification result. Downstream stages read the refreshed effective
        profile, so recommendations, skill gap, and roadmap are regenerated.
        """
        try:
            self.evidence_gate.reassess_user_evidence(state["user_id"])
            return {
                "stage": "evidence_gate",
                "final_status": "RUNNING",
            }
        except Exception as exc:
            return self._stage_error_update("evidence_gate", exc, state)

    def _career_recommendation(self, state: CareerWorkflowState) -> dict:
        try:
            recommendations = self.career_recommendation_agent.run(state["user_id"])
            if not recommendations:
                raise ValueError("career recommendation agent returned no canonical careers")
            target_id = state.get("target_career_id")
            canonical_ids = {item.career_id for item in recommendations}
            if target_id is not None and target_id not in canonical_ids:
                raise ValueError(
                    f"target_career_id={target_id!r} is not among the canonical recommendations"
                )
            if target_id is None:
                target_id = recommendations[0].career_id
            return {
                "recommendations": recommendations,
                "target_career_id": target_id,
                "skill_gap": None,
                "roadmap": None,
                "verification": None,
                "revision_target": None,
                "stage": "career_recommendation",
                "final_status": "RUNNING",
            }
        except Exception as exc:
            return self._stage_error_update("career_recommendation", exc, state)

    def _skill_gap_analysis(self, state: CareerWorkflowState) -> dict:
        try:
            target_id = state.get("target_career_id")
            if not target_id:
                raise ValueError("no target career was selected")
            result = self.skill_gap_agent.run(state["user_id"], target_id)
            if result.skill_gap.career_id != target_id:
                raise ValueError(
                    "skill-gap agent returned a result for a different target career"
                )
            return {
                "skill_gap": result,
                "roadmap": None,
                "verification": None,
                "stage": "skill_gap_analysis",
                "final_status": "RUNNING",
            }
        except Exception as exc:
            return self._stage_error_update("skill_gap_analysis", exc, state)

    def _learning_roadmap(self, state: CareerWorkflowState) -> dict:
        try:
            gap = state.get("skill_gap")
            if gap is None:
                raise ValueError("skill-gap result is required before roadmap generation")
            result = self.learning_roadmap_agent.run(gap)
            if result.skill_gap.model_dump() != gap.skill_gap.model_dump():
                raise ValueError(
                    "roadmap agent returned a result that does not preserve the skill-gap output"
                )
            return {
                "roadmap": result,
                "verification": None,
                "stage": "learning_roadmap",
                "final_status": "RUNNING",
            }
        except Exception as exc:
            return self._stage_error_update("learning_roadmap", exc, state)

    def _verification(self, state: CareerWorkflowState) -> dict:
        try:
            recommendations = state.get("recommendations")
            gap = state.get("skill_gap")
            roadmap = state.get("roadmap")
            if recommendations is None or gap is None or roadmap is None:
                raise ValueError(
                    "recommendations, skill-gap result, and roadmap are required for verification"
                )
            result = self.verification_agent.run(
                redact_recommendations(recommendations),
                redact_skill_gap_analysis(gap),
                redact_roadmap(roadmap),
            )
            return {
                "verification": result,
                "first_pass_verification_status": (
                    result.status if state.get("first_pass_verification_status") is None
                    else state.get("first_pass_verification_status")
                ),
                "revision_target": None,
                "stage": "verification",
                "final_status": "RUNNING",
            }
        except Exception as exc:
            return self._stage_error_update("verification", exc, state)

    @staticmethod
    def _revision_target(state: CareerWorkflowState) -> RevisionTarget | None:
        verification = state.get("verification")
        if verification is None:
            return None
        targets: set[RevisionTarget] = set()
        for check in verification.checks:
            if check.status == "PASS":
                continue
            if check.check.startswith("recommendation."):
                targets.add("career_recommendation")
            elif check.check.startswith("skill_gap."):
                targets.add("skill_gap")
            elif check.check.startswith("roadmap."):
                targets.add("roadmap")
            elif check.check.startswith("user_evidence."):
                targets.add("evidence")
        for claim in verification.unsupported_claims:
            if claim.component.startswith("recommendation:"):
                targets.add("career_recommendation")
            elif claim.component == "skill_gap_narrative":
                targets.add("skill_gap")
            elif claim.component == "roadmap_summary":
                targets.add("roadmap")

        # Upstream agents take precedence; their downstream results are
        # regenerated naturally by the graph's existing stage edges. Evidence
        # acceptance is upstream of every skill-derived output.
        candidates: tuple[RevisionTarget, ...] = (
            "evidence", "career_recommendation", "skill_gap", "roadmap",
        )
        for candidate in candidates:
            if candidate in targets:
                return candidate
        return None

    def _verification_decision(self, state: CareerWorkflowState) -> dict:
        verification = state.get("verification")
        if verification is None:
            return self._error_update(
                "verification_decision",
                ValueError("verification result is missing"),
            )
        is_verified = (
            verification.status == "PASS"
            and all(check.status == "PASS" for check in verification.checks)
            and not verification.unsupported_claims
            and not verification.required_revision
        )
        if is_verified:
            return {
                "stage": "final_result",
                "final_status": "VERIFIED",
                "revision_target": None,
            }

        target = self._revision_target(state)
        if target is None:
            return {
                "stage": "final_result",
                "final_status": "VERIFICATION_FAILED",
                "revision_target": None,
            }
        if state["revision_count"] >= self.max_revisions:
            return {
                "stage": "final_result",
                "final_status": "REVISION_LIMIT_REACHED",
                "revision_target": target,
            }
        return {
            "stage": "revision_routing",
            "revision_count": state["revision_count"] + 1,
            "revision_target": target,
            "final_status": "RUNNING",
        }

    @staticmethod
    def _after_stage(state: CareerWorkflowState, next_node: str) -> str:
        return "final_result" if state["final_status"] == "ERROR" else next_node

    @staticmethod
    def _after_decision(state: CareerWorkflowState) -> str:
        if state["final_status"] != "RUNNING":
            return "final_result"
        return {
            "career_recommendation": "career_recommendation",
            "skill_gap": "skill_gap_analysis",
            "roadmap": "learning_roadmap",
            "evidence": "evidence_gate",
        }.get(state.get("revision_target"), "final_result")

    @staticmethod
    def _finish(state: CareerWorkflowState) -> dict:
        if state.get("verification") is None and state.get("configuration_id") == "B3":
            return {"stage": "final_result", "final_status": "UNVERIFIED"}
        verification = state.get("verification")
        final_status = state["final_status"]
        if final_status == "VERIFIED" and (
            verification is None
            or verification.status != "PASS"
            or any(check.status != "PASS" for check in verification.checks)
            or verification.unsupported_claims
            or verification.required_revision
        ):
            return {
                "stage": "final_result",
                "final_status": "VERIFICATION_FAILED",
                "errors": [{
                    "stage": "final_result",
                    "error_type": "InvalidVerificationState",
                    "message": "A workflow cannot be VERIFIED without a PASS verification result.",
                }],
            }
        return {"stage": "final_result"}

    def _compile(self):
        graph = StateGraph(CareerWorkflowState)
        graph.add_node("profile_analysis", self._profile_analysis)
        graph.add_node("evidence_gate", self._evidence_gate)
        graph.add_node("career_recommendation", self._career_recommendation)
        graph.add_node("skill_gap_analysis", self._skill_gap_analysis)
        graph.add_node("learning_roadmap", self._learning_roadmap)
        graph.add_node("verification", self._verification)
        graph.add_node("verification_decision", self._verification_decision)
        graph.add_node("final_result", self._finish)

        graph.add_edge(START, "profile_analysis")
        graph.add_conditional_edges(
            "profile_analysis",
            self._after_profile,
            {
                "evidence_gate": "evidence_gate",
                "career_recommendation": "career_recommendation",
                "final_result": "final_result",
            },
        )
        graph.add_conditional_edges(
            "career_recommendation",
            lambda state: self._after_stage(state, "skill_gap_analysis"),
            {"skill_gap_analysis": "skill_gap_analysis", "final_result": "final_result"},
        )
        graph.add_conditional_edges(
            "skill_gap_analysis",
            lambda state: self._after_stage(state, "learning_roadmap"),
            {"learning_roadmap": "learning_roadmap", "final_result": "final_result"},
        )
        graph.add_conditional_edges(
            "learning_roadmap",
            lambda state: self._after_stage(
                state, "verification" if self.configuration.uses_verification_agent else "final_result"
            ),
            {"verification": "verification", "final_result": "final_result"},
        )
        graph.add_conditional_edges(
            "verification",
            lambda state: "final_result" if state["final_status"] == "ERROR" else "verification_decision",
            {"final_result": "final_result", "verification_decision": "verification_decision"},
        )
        graph.add_conditional_edges(
            "verification_decision",
            self._after_decision,
            {
                "evidence_gate": "evidence_gate",
                "career_recommendation": "career_recommendation",
                "skill_gap_analysis": "skill_gap_analysis",
                "learning_roadmap": "learning_roadmap",
                "final_result": "final_result",
            },
        )
        graph.add_conditional_edges(
            "evidence_gate",
            lambda state: self._after_stage(state, "career_recommendation"),
            {"career_recommendation": "career_recommendation", "final_result": "final_result"},
        )
        graph.add_edge("final_result", END)
        return graph.compile()

    def run(
        self,
        user_id: int,
        target_career_id: str | None = None,
        raw_profile_text: str | None = None,
        observer: Callable[[str, dict], None] | None = None,
        profile_bundle: FrozenProfileBundle | dict | None = None,
        career_labels: list[CareerOutputLabel] | None = None,
    ) -> CareerWorkflowState:
        """Run the compiled graph and return all original outputs plus findings."""
        initial_state: CareerWorkflowState = {
            "user_id": user_id,
            "configuration_id": self.configuration.config_id,
            "first_pass_verification_status": None,
            "target_career_id": target_career_id,
            "profile_result": None,
            "recommendations": None,
            "skill_gap": None,
            "roadmap": None,
            "verification": None,
            "stage": "start",
            "revision_count": 0,
            "revision_target": None,
            "final_status": "RUNNING",
            "errors": [],
            "baseline_result": None,
            "input_profile_bundle": None,
        }
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            initial_state.update(self._error_update(
                "input_validation",
                ValueError("user_id must be a positive integer"),
            ))
            return initial_state
        if self.configuration.config_id in {"B0", "B2"}:
            if target_career_id is not None:
                return {**initial_state, **self._error_update(
                    "input_validation",
                    ValueError("B0/B2 cannot receive a preselected career or ground-truth label"),
                )}
            if profile_bundle is None and raw_profile_text is not None:
                try:
                    profile_bundle = self.extract_profile_bundle(raw_profile_text)
                except Exception as exc:
                    return {**initial_state, **self._error_update("profile_bundle_extraction", exc)}
            if profile_bundle is None:
                return self._error_update(
                    "input_validation",
                    ValueError("B0/B2 require the shared pre-normalization profile_bundle"),
                ) | {
                    "user_id": user_id,
                    "configuration_id": self.configuration.config_id,
                    "first_pass_verification_status": None,
                    "target_career_id": target_career_id,
                    "profile_result": None,
                    "recommendations": None,
                    "skill_gap": None,
                    "roadmap": None,
                    "verification": None,
                    "stage": "input_validation",
                    "revision_count": 0,
                    "final_status": "ERROR",
                    "baseline_result": None,
                    "input_profile_bundle": None,
                }
            try:
                result = self.baseline_agent.run(
                    FrozenProfileBundle.model_validate(profile_bundle),
                    career_labels=career_labels or self.career_labels,
                )
                return {
                    **initial_state,
                    "baseline_result": result,
                    "input_profile_bundle": None,
                    "recommendations": result.recommendations,
                    "stage": "final_result",
                    "final_status": "UNVERIFIED",
                }
            except Exception as exc:
                return {**initial_state, **self._error_update("baseline_inference", exc)}
        if not self.configuration.uses_verification_agent:
            # The graph's verification and revision nodes are unreachable in B3.
            initial_state["revision_count"] = 0
        if target_career_id is not None and (
            not isinstance(target_career_id, str) or not target_career_id.strip()
        ):
            initial_state.update(self._error_update(
                "input_validation",
                ValueError("target_career_id must be a non-empty string when supplied"),
            ))
            return initial_state
        if raw_profile_text is not None and (
            not isinstance(raw_profile_text, str) or not raw_profile_text.strip()
        ):
            initial_state.update(self._error_update(
                "input_validation",
                ValueError("raw_profile_text must be a non-empty string when supplied"),
            ))
            return initial_state
        if profile_bundle is not None:
            if raw_profile_text is not None:
                initial_state.update(self._error_update(
                    "input_validation", ValueError("supply profile_bundle or raw_profile_text, not both")
                ))
                return initial_state
            try:
                initial_state["input_profile_bundle"] = FrozenProfileBundle.model_validate(profile_bundle)
            except Exception as exc:
                initial_state.update(self._error_update("input_validation", exc))
                return initial_state
        if raw_profile_text is not None:
            initial_state["redacted_profile_text"] = redact_pii(raw_profile_text).redacted_text
        try:
            if observer is None:
                result = self.graph.invoke(initial_state)
            else:
                result = None
                for mode, chunk in self.graph.stream(
                    initial_state, stream_mode=["updates", "values"]
                ):
                    if mode == "values":
                        result = chunk
                    elif mode == "updates" and isinstance(chunk, dict):
                        for node, update in chunk.items():
                            try:
                                observer("node_update", {"node": node, "update": update})
                            except Exception as exc:
                                logger.warning(
                                    "Workflow inspection observer failed (%s).",
                                    type(exc).__name__,
                                )
                if result is None:
                    raise RuntimeError("Observed workflow completed without a final state.")
            result.pop("redacted_profile_text", None)
            result.pop("input_profile_bundle", None)
            return result
        except Exception as exc:
            # Graph/runtime errors are also returned as explicit workflow
            # failures, not as verification success or unstructured exceptions.
            initial_state.pop("redacted_profile_text", None)
            safe_message = (
                "Workflow execution failed; submitted profile details were omitted."
                if raw_profile_text is not None else None
            )
            initial_state.update(self._error_update("workflow", exc, safe_message=safe_message))
            return initial_state

    def extract_profile_bundle(self, extracted_cv_text: str) -> FrozenProfileBundle:
        """Extract one redacted pre-normalization bundle for paired configurations."""
        if self.llm_client is None:
            raise RuntimeError("profile bundle extraction requires the configured LLM client")
        return FrozenProfileBundleExtractor(self.llm_client).run(extracted_cv_text)


def build_career_workflow(
    *,
    llm_client: LLMClient | None = None,
    max_revisions: int = 2,
    profile_agent: ProfileAgent | None = None,
    career_recommendation_agent: CareerRecommendationAgent | None = None,
    skill_gap_agent: SkillGapAgent | None = None,
    learning_roadmap_agent: LearningRoadmapAgent | None = None,
    verification_agent: VerificationAgent | None = None,
    configuration_id: str = "F",
    career_labels: list[CareerOutputLabel] | None = None,
):
    """Construct the compiled StateGraph with optional agent substitutions."""
    workflow = CareerWorkflow(
        llm_client=llm_client,
        max_revisions=max_revisions,
        profile_agent=profile_agent,
        career_recommendation_agent=career_recommendation_agent,
        skill_gap_agent=skill_gap_agent,
        learning_roadmap_agent=learning_roadmap_agent,
        verification_agent=verification_agent,
        configuration_id=configuration_id,
        career_labels=career_labels,
    )
    return workflow if workflow.graph is None else workflow.graph
