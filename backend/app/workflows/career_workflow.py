"""Step 13: stateful orchestration for the existing career agents."""
from typing import Literal, NotRequired, TypedDict

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
from app.services import retrieval_service as rs
from app.services import user_service as us


WorkflowFinalStatus = Literal[
    "RUNNING",
    "VERIFIED",
    "VERIFICATION_FAILED",
    "REVISION_LIMIT_REACHED",
    "ERROR",
]
RevisionTarget = Literal["career_recommendation", "skill_gap", "roadmap"]


class WorkflowError(TypedDict):
    stage: str
    error_type: str
    message: str


class CareerWorkflowState(TypedDict):
    """Minimum state needed to coordinate the existing agent contracts."""

    user_id: int
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
    ):
        if not isinstance(max_revisions, int) or isinstance(max_revisions, bool) or max_revisions < 0:
            raise ValueError("max_revisions must be a non-negative integer")
        self.max_revisions = max_revisions
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
        self.graph = self._compile()

    @staticmethod
    def _error_update(
        stage: str,
        exc: Exception,
        *,
        safe_message: str | None = None,
    ) -> dict:
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
            return {
                "profile_result": result,
                "stage": "profile_analysis",
                "final_status": "RUNNING",
            }
        except Exception as exc:
            return self._error_update(
                "profile_analysis",
                exc,
                safe_message="Profile analysis failed; submitted profile details were omitted.",
            )

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
            result = self.verification_agent.run(recommendations, gap, roadmap)
            return {
                "verification": result,
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
        for claim in verification.unsupported_claims:
            if claim.component.startswith("recommendation:"):
                targets.add("career_recommendation")
            elif claim.component == "skill_gap_narrative":
                targets.add("skill_gap")
            elif claim.component == "roadmap_summary":
                targets.add("roadmap")

        # Upstream agents take precedence; their downstream results are
        # regenerated naturally by the graph's existing stage edges.
        candidates: tuple[RevisionTarget, ...] = (
            "career_recommendation", "skill_gap", "roadmap",
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
        }.get(state.get("revision_target"), "final_result")

    @staticmethod
    def _finish(state: CareerWorkflowState) -> dict:
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
        graph.add_node("career_recommendation", self._career_recommendation)
        graph.add_node("skill_gap_analysis", self._skill_gap_analysis)
        graph.add_node("learning_roadmap", self._learning_roadmap)
        graph.add_node("verification", self._verification)
        graph.add_node("verification_decision", self._verification_decision)
        graph.add_node("final_result", self._finish)

        graph.add_edge(START, "profile_analysis")
        graph.add_conditional_edges(
            "profile_analysis",
            lambda state: self._after_stage(state, "career_recommendation"),
            {"career_recommendation": "career_recommendation", "final_result": "final_result"},
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
            lambda state: self._after_stage(state, "verification"),
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
                "career_recommendation": "career_recommendation",
                "skill_gap_analysis": "skill_gap_analysis",
                "learning_roadmap": "learning_roadmap",
                "final_result": "final_result",
            },
        )
        graph.add_edge("final_result", END)
        return graph.compile()

    def run(
        self,
        user_id: int,
        target_career_id: str | None = None,
        raw_profile_text: str | None = None,
    ) -> CareerWorkflowState:
        """Run the compiled graph and return all original outputs plus findings."""
        initial_state: CareerWorkflowState = {
            "user_id": user_id,
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
        }
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            initial_state.update(self._error_update(
                "input_validation",
                ValueError("user_id must be a positive integer"),
            ))
            return initial_state
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
        if raw_profile_text is not None:
            initial_state["redacted_profile_text"] = redact_pii(raw_profile_text).redacted_text
        try:
            result = self.graph.invoke(initial_state)
            result.pop("redacted_profile_text", None)
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


def build_career_workflow(
    *,
    llm_client: LLMClient | None = None,
    max_revisions: int = 2,
    profile_agent: ProfileAgent | None = None,
    career_recommendation_agent: CareerRecommendationAgent | None = None,
    skill_gap_agent: SkillGapAgent | None = None,
    learning_roadmap_agent: LearningRoadmapAgent | None = None,
    verification_agent: VerificationAgent | None = None,
):
    """Construct the compiled StateGraph with optional agent substitutions."""
    return CareerWorkflow(
        llm_client=llm_client,
        max_revisions=max_revisions,
        profile_agent=profile_agent,
        career_recommendation_agent=career_recommendation_agent,
        skill_gap_agent=skill_gap_agent,
        learning_roadmap_agent=learning_roadmap_agent,
        verification_agent=verification_agent,
    ).graph
