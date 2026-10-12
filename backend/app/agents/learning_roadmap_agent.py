"""Learning roadmap generation from the existing deterministic skill gap."""
import json
import re

from app.agents.llm_client import LLMClient
from app.schemas.learning_roadmap import LearningRoadmapItem, LearningRoadmapOut
from app.schemas.retrieval import OccupationalContextOut
from app.schemas.skill_gap import SkillGapItem, SkillGapResult
from app.schemas.skill_gap_agent import SkillGapAnalysisOut
from app.services import retrieval_service as rs


LLM_MAX_TOKENS = 500

ROADMAP_SYSTEM_PROMPT = """You write a short overview of a learning-focus list for a career.
The supplied skill-gap result is authoritative. Return exactly one JSON object:
{"summary": "<one or two sentences>"}

Do not add, remove, rename, rank, score, or sequence any skill. Do not suggest or name
courses, learning resources, certifications, prerequisites, technologies, proficiency
levels, or timelines. Do not add facts beyond the supplied career and learning-focus
items. The structured roadmap items are generated separately and cannot be changed."""

_UNSUPPORTED_CONCEPTS = re.compile(
    r"\b(?:courses?|tutorials?|resources?|bootcamps?|certifications?|certificates?|"
    r"prerequisites?|dependencies?|proficiency|beginner|intermediate|advanced|expert|"
    r"priorit\w*|rank(?:ing)?|score|percent(?:age)?|weeks?|months?|days?)\b|\d",
    re.IGNORECASE,
)
_WORDS = re.compile(r"[A-Za-z]+")
_SAFE_SUMMARY_WORDS = frozenset(
    "a and are based contains existing focus focuses for from has have in is "
    "items learning list not occupational on reflects result roadmap skill skills "
    "supplied the these this to follows with evidence knowledge base gap career "
    "recorded linked required develop".split()
)


class RoadmapContextError(ValueError):
    """The skill-gap result cannot be matched to the occupational KB context."""


def _gap_result(result: SkillGapResult | SkillGapAnalysisOut) -> SkillGapResult:
    return result.skill_gap if isinstance(result, SkillGapAnalysisOut) else result


def _word_pattern(value: str) -> re.Pattern:
    words = r"\s+".join(re.escape(part) for part in value.split())
    return re.compile(r"(?<![A-Za-z0-9_])" + words + r"(?![A-Za-z0-9_])", re.IGNORECASE)


class LearningRoadmapAgent:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client

    def _get_context(self, gap: SkillGapResult) -> OccupationalContextOut:
        context = rs.get_occupational_context(gap.career_id)
        if context is None:
            raise RoadmapContextError(
                f"No occupational knowledge-base context for career_id={gap.career_id!r}"
            )
        if (context.career.career_id, context.career.canonical_name) != (
            gap.career_id, gap.canonical_name
        ):
            raise RoadmapContextError("Skill-gap career does not match occupational knowledge-base context")
        return context

    def _build_items(
        self, gap: SkillGapResult, context: OccupationalContextOut
    ) -> list[LearningRoadmapItem]:
        targets: dict[str, list[SkillGapItem]] = {}
        for item in gap.matched_claimed_only + gap.missing:
            targets.setdefault(item.skill_id, []).append(item)

        roadmap_items: list[LearningRoadmapItem] = []
        for career_skill in context.career_skills:
            candidates = targets.get(career_skill.skill.skill_id)
            if not candidates:
                continue

            item = candidates.pop(0)
            if (
                item.canonical_name != career_skill.skill.canonical_name
                or item.evidence_class != career_skill.evidence_class
                or item.kb_confidence != career_skill.confidence
            ):
                raise RoadmapContextError(
                    f"Skill-gap metadata does not match the knowledge base for {item.skill_id}"
                )
            roadmap_items.append(LearningRoadmapItem(
                skill_id=item.skill_id,
                canonical_name=item.canonical_name,
                gap_status=item.status,
                evidence_class=item.evidence_class,
                kb_confidence=item.kb_confidence,
                knowledge_base_basis=career_skill.evidence_source_text,
                learning_action=(
                    "add_linked_evidence"
                    if item.status == "matched_claimed_only"
                    else "develop_skill"
                ),
            ))

        unmatched_targets = [sid for sid, items in targets.items() if items]
        if unmatched_targets:
            raise RoadmapContextError(
                "Skill-gap requirements are absent from occupational context: "
                + ", ".join(unmatched_targets)
            )
        return roadmap_items

    def _summary_prompt(self, gap: SkillGapResult, items: list[LearningRoadmapItem]) -> str:
        return json.dumps({
            "career": gap.canonical_name,
            "focus_items": [
                {
                    "skill_id": item.skill_id,
                    "skill": item.canonical_name,
                    "gap_status": item.gap_status,
                    "knowledge_base_basis": item.knowledge_base_basis,
                }
                for item in items
            ],
        }, ensure_ascii=False, indent=2)

    def _validate_summary(
        self,
        response: object,
        gap: SkillGapResult,
        items: list[LearningRoadmapItem],
        career_skill_names: set[str],
        technology_names: set[str],
    ) -> str:
        if not isinstance(response, dict) or set(response) != {"summary"}:
            raise ValueError("LLM output must contain only a summary field")
        summary = response["summary"]
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 600:
            raise ValueError("LLM summary must be a non-empty string of at most 600 characters")
        summary = summary.strip()
        if _UNSUPPORTED_CONCEPTS.search(summary):
            raise ValueError("LLM summary introduces unsupported resources, requirements, ranking, or numeric claims")

        allowed_names = {gap.canonical_name.lower()}
        allowed_names.update(item.canonical_name.lower() for item in items)
        unsupported_names = (career_skill_names | technology_names) - allowed_names
        if any(_word_pattern(name).search(summary) for name in unsupported_names if name.strip()):
            raise ValueError("LLM summary mentions a skill or technology outside the roadmap context")

        allowed_words = set(_SAFE_SUMMARY_WORDS)
        allowed_words.update(
            word.lower()
            for value in (
                gap.canonical_name,
                gap.domain,
                *(item.canonical_name for item in items),
                *(item.knowledge_base_basis for item in items),
            )
            for word in _WORDS.findall(value)
        )
        unsupported_words = {
            word.lower() for word in _WORDS.findall(summary)
        } - allowed_words
        if unsupported_words:
            raise ValueError(
                "LLM summary contains words outside the supplied career and knowledge-base context: "
                + ", ".join(sorted(unsupported_words))
            )
        return summary

    def _fallback_summary(self, gap: SkillGapResult, items: list[LearningRoadmapItem]) -> str:
        missing_count = sum(item.gap_status == "missing" for item in items)
        claimed_count = sum(item.gap_status == "matched_claimed_only" for item in items)
        return (
            f"The learning focus for {gap.canonical_name} follows the supplied skill-gap result: "
            f"{missing_count} required skill(s) to develop and {claimed_count} claimed skill(s) "
            "for which linked evidence is not yet recorded. Items are not ranked; the knowledge "
            "base does not provide courses, resources, prerequisites, or proficiency targets."
        )

    def run(self, result: SkillGapResult | SkillGapAnalysisOut) -> LearningRoadmapOut:
        """Build focus items from an existing Step 9/10 result; never recalculate the gap."""
        gap = _gap_result(result)
        context = self._get_context(gap)
        items = self._build_items(gap, context)

        if self.llm_client is None:
            return LearningRoadmapOut(
                skill_gap=gap, items=items, summary=self._fallback_summary(gap, items),
                narrative_source="fallback-template",
            )

        try:
            response = self.llm_client.complete_json(
                system=ROADMAP_SYSTEM_PROMPT,
                user=self._summary_prompt(gap, items),
                max_tokens=LLM_MAX_TOKENS,
            )
            summary = self._validate_summary(
                response,
                gap,
                items,
                {item.skill.canonical_name for item in context.career_skills},
                {technology.technology_name
                 for technologies in context.technologies.values() for technology in technologies},
            )
            return LearningRoadmapOut(
                skill_gap=gap, items=items, summary=summary, narrative_source="llm",
            )
        except Exception as exc:
            return LearningRoadmapOut(
                skill_gap=gap, items=items, summary=self._fallback_summary(gap, items),
                narrative_source="fallback-template",
                llm_error=f"LLM roadmap summary rejected or failed: {type(exc).__name__}: {str(exc)[:200]}",
            )
