"""LLM decision paths for B0 and B2, isolated from deterministic engines."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.llm_client import LLMClient
from app.services.pii_redaction_service import redact_pii
from app.services import retrieval_service as rs


class SkillMention(BaseModel):
    model_config = {"extra": "forbid"}
    mention_id: str
    text: str
    proficiency: str | None = Field(default=None, strict=True)
    evidence_spans: list[str] = Field(default_factory=list)


class FrozenProfileBundle(BaseModel):
    """Configuration-independent extraction, before any OKB normalization."""
    model_config = {"extra": "forbid"}
    extracted_cv_text: str
    skill_mentions: list[SkillMention] = Field(default_factory=list)
    experience: list["ExperienceFact"] = Field(default_factory=list)
    education: list["EducationFact"] = Field(default_factory=list)
    projects: list["ProjectFact"] = Field(default_factory=list)
    certifications: list["CertificationFact"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _mentions_are_grounded_in_cv(self):
        cv = " ".join(self.extracted_cv_text.casefold().split())
        for mention in self.skill_mentions:
            text = " ".join(mention.text.casefold().split())
            if not text or text not in cv:
                raise ValueError("skill mentions must be explicit text from the extracted CV")
            for span in mention.evidence_spans:
                normalized_span = " ".join(span.casefold().split())
                if not normalized_span or normalized_span not in cv:
                    raise ValueError("evidence spans must quote text from the extracted CV")
        return self


class ExperienceFact(BaseModel):
    model_config = {"extra": "forbid"}
    company: str | None = None
    role_title: str
    employment_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class EducationFact(BaseModel):
    model_config = {"extra": "forbid"}
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ProjectFact(BaseModel):
    model_config = {"extra": "forbid"}
    title: str
    description: str | None = None
    url: str | None = None
    role: str | None = None


class CertificationFact(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    issuer: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None
    credential_url: str | None = None


class CareerOutputLabel(BaseModel):
    model_config = {"extra": "forbid"}
    career_id: str
    career_name: str


class RankedCareer(BaseModel):
    model_config = {"extra": "forbid"}
    career_id: str
    rank: int = Field(ge=1)
    rationale: str
    fit_score: float | None = None


class B0Capability(BaseModel):
    model_config = {"extra": "forbid"}
    status: Literal["NOT_APPLICABLE"] = "NOT_APPLICABLE"
    reason: str


class B2EvidenceReference(BaseModel):
    """CV source trace for a skill-mention relationship, not semantic proof."""
    model_config = {"extra": "forbid"}
    mention_id: str
    evidence_spans: list[str] = Field(min_length=1)


class B2SkillGap(BaseModel):
    model_config = {"extra": "forbid"}
    career_id: str
    matched_evidenced: list[str]
    matched_claimed_only: list[str]
    missing: list[str]
    unmatched_user_claims: list[str]
    claim_matches: dict[str, list[str]]
    claim_evidence: dict[str, list[B2EvidenceReference]] = Field(default_factory=dict)
    evidence_validation_scope: Literal["structural_source_trace_only"] = "structural_source_trace_only"


class BaselineInferenceResult(BaseModel):
    model_config = {"extra": "forbid"}
    configuration_id: Literal["B0", "B2"]
    recommendations: list[RankedCareer]
    skill_gap: B2SkillGap | B0Capability
    roadmap: B0Capability
    verification: B0Capability

    @model_validator(mode="after")
    def _ranking_is_ordered(self):
        ids = [r.career_id for r in self.recommendations]
        ranks = [r.rank for r in self.recommendations]
        if len(ids) != len(set(ids)) or ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("recommendations must have unique career IDs and contiguous ranks")
        if self.configuration_id == "B0" and not isinstance(self.skill_gap, B0Capability):
            raise ValueError("B0 skill-gap output must be explicitly NOT_APPLICABLE")
        if self.configuration_id == "B2" and not isinstance(self.skill_gap, B2SkillGap):
            raise ValueError("B2 must return structured skill-gap categories")
        return self


class BaselineInferenceAgent:
    """One LLM decision call, with configuration-specific context and guards."""
    def __init__(self, *, llm_client: LLMClient, configuration_id: str):
        if configuration_id not in {"B0", "B2"}:
            raise ValueError("BaselineInferenceAgent supports only B0 and B2")
        self.llm_client = llm_client
        self.configuration_id = configuration_id

    @staticmethod
    def system_prompt(configuration_id: str) -> str:
        if configuration_id not in {"B0", "B2"}:
            raise ValueError("BaselineInferenceAgent supports only B0 and B2")
        system = (
            "Rank the supplied career output labels using only the supplied profile. "
            "Do not invent career IDs or evidence. Return exactly one JSON object, not a "
            "top-level array, with this shape: "
            '{"recommendations":[{"career_id":str,"rank":int,"rationale":str}]}. '
            "Include exactly 10 recommendations with unique career IDs and ranks 1-10."
        )
        if configuration_id == "B0":
            return system + " Do not infer or return skill gaps or a roadmap."
        return system + (
            ' Also include a top-level "skill_gap" object for the top-ranked career, '
            "decided from the supplied complete Career-Skill relations and profile. Return "
            "skill_gap as {career_id, matched_evidenced, matched_claimed_only, missing, "
            "unmatched_user_claims, claim_matches, claim_evidence}. The three category lists contain required "
            "skill_id values; every required skill of that career must occur in exactly one "
            "of matched_evidenced, matched_claimed_only, or missing. Every skill in "
            "matched_evidenced or matched_claimed_only must have at least one supporting "
            "mention_id in claim_matches; a skill with no supporting mention must be in "
            "missing. claim_matches maps each matched skill_id to all supporting mention_id "
            "values; one mention may support several matched skills. Every mention_id not "
            "used in claim_matches must appear in unmatched_user_claims, and no mention_id "
            "may appear in both. "
            "matched_evidenced requires a mention with a non-empty evidence span; "
            "matched_claimed_only requires a mention without evidence spans. "
            "claim_evidence maps every matched skill_id to one object per claim_matches mention: "
            "{mention_id, evidence_spans}. Cite exact supplied evidence_spans for evidenced "
            "mentions. For a claimed-only mention with no evidence_spans, cite its exact mention "
            "text as a claim span; that traces the claim but is not corroborating evidence. This "
            "is structural source tracing only and does not prove semantic entailment. "
            "Do not return scores. Build claim_matches first, then set matched_evidenced and "
            "matched_claimed_only from its keys according to the evidence rule, and put only "
            "the remaining required skills in missing. Before returning, verify that every "
            "matched skill has at least one mention in claim_matches, and that every "
            "mention_id appears in claim_matches or unmatched_user_claims but never in both."
        )

    def run(
        self,
        profile: FrozenProfileBundle,
        *,
        career_labels: list[CareerOutputLabel] | None = None,
    ) -> BaselineInferenceResult:
        profile = FrozenProfileBundle.model_validate(profile)
        relations = None
        if self.configuration_id == "B0":
            if not career_labels or len(career_labels) != 10:
                raise ValueError("B0 requires the fixed 10-career output label list")
            labels = [CareerOutputLabel.model_validate(row) for row in career_labels]
            if len({row.career_id for row in labels}) != 10:
                raise ValueError("B0 career output labels must contain 10 unique IDs")
        else:
            careers = rs.get_all_careers()
            if len(careers) != 10:
                raise ValueError("B2 requires exactly 10 approved careers in the OKB")
            labels = [CareerOutputLabel(career_id=c.career_id, career_name=c.canonical_name) for c in careers]
            relations = []
            for career in careers:
                rows = rs.get_career_skills(career.career_id)
                relations.append({
                    "career_id": career.career_id,
                    "career_name": career.canonical_name,
                    "domain": career.domain,
                    "skills": [{
                        "relationship_id": row.relationship_id,
                        "skill_id": row.skill.skill_id,
                        "canonical_name": row.skill.canonical_name,
                        "skill_group_id": row.skill.skill_group_id,
                        "skill_status": row.skill.status,
                        "evidence_class": row.evidence_class,
                        "confidence": row.confidence,
                        "mapping_method": row.mapping_method,
                        "evidence_source_text": row.evidence_source_text,
                    } for row in rows],
                })

        system = self.system_prompt(self.configuration_id)
        if self.configuration_id == "B0":
            context = {"career_output_labels": [x.model_dump() for x in labels], "profile": profile.model_dump()}
        else:
            context = {
                "careers_and_complete_relations": relations,
                "profile": profile.model_dump(),
            }
        raw = self.llm_client.complete_json(system=system, user=json.dumps(context), max_tokens=5000)
        valid_careers = {label.career_id for label in labels}
        rows = raw.get("recommendations") if isinstance(raw, dict) else None
        if not isinstance(rows, list) or len(rows) != 10:
            raise ValueError("LLM must rank all 10 career output labels")
        recommendations = [RankedCareer.model_validate(row) for row in rows]
        if any(row.fit_score is not None for row in recommendations):
            raise ValueError("LLM-only baseline outputs must not contain career-fit scores")
        if {row.career_id for row in recommendations} != valid_careers:
            raise ValueError("LLM ranking contains missing or unsupported career IDs")
        recommendations.sort(key=lambda row: row.rank)

        no_roadmap = B0Capability(reason="This configuration does not generate learning roadmaps.")
        no_verification = B0Capability(reason="This configuration does not run verification.")
        if self.configuration_id == "B0":
            gap: B0Capability | B2SkillGap = B0Capability(
                reason="B0 has no occupational requirements and does not perform skill-gap analysis."
            )
        else:
            career_id = recommendations[0].career_id
            required = {
                row["skill_id"] for rel in relations if rel["career_id"] == career_id
                for row in rel["skills"]
            }
            mention_ids = {mention.mention_id for mention in profile.skill_mentions}
            gap = B2SkillGap.model_validate(raw.get("skill_gap"))
            if gap.career_id != career_id:
                raise ValueError("B2 skill-gap career must match the top-ranked career")
            categories = [gap.matched_evidenced, gap.matched_claimed_only, gap.missing]
            flattened = [skill_id for category in categories for skill_id in category]
            if len(flattened) != len(set(flattened)) or set(flattened) != required:
                raise ValueError("B2 categories must classify each required skill exactly once")
            if not set(gap.unmatched_user_claims).issubset(mention_ids):
                raise ValueError("B2 unmatched claims must reference supplied skill mention IDs")
            if any(
                mention_id not in mention_ids
                for mention_ids_for_skill in gap.claim_matches.values()
                for mention_id in mention_ids_for_skill
            ):
                raise ValueError("B2 claim_matches references an unknown mention ID")
            mapped_mentions = [mention_id for ids in gap.claim_matches.values() for mention_id in ids]
            if any(skill_id not in required for skill_id in gap.claim_matches):
                raise ValueError("B2 claim_matches contains an unsupported skill ID")
            # A single mention may support more than one matched skill; the schema field is
            # "all supporting mention_id values". Only forbid repeats within one skill and
            # overlap with unmatched claims.
            if any(len(ids) != len(set(ids)) for ids in gap.claim_matches.values()):
                raise ValueError("B2 claim_matches must not repeat a mention for one skill")
            if set(mapped_mentions) & set(gap.unmatched_user_claims):
                raise ValueError("B2 profile mentions cannot be both matched and unmatched")
            if set(mapped_mentions) | set(gap.unmatched_user_claims) != mention_ids:
                raise ValueError("B2 must account for every supplied profile skill mention")
            mention_by_id = {item.mention_id: item for item in profile.skill_mentions}
            if set(gap.claim_evidence) != set(gap.claim_matches):
                raise ValueError("B2 evidence relationships must cover exactly the claim_matches skills")
            statuses = {
                skill_id: status
                for status, skill_ids in zip(
                    ("matched_evidenced", "matched_claimed_only", "missing"), categories
                )
                for skill_id in skill_ids
            }
            for skill_id, mention_ids_for_skill in gap.claim_matches.items():
                if statuses.get(skill_id) == "missing":
                    raise ValueError(f"B2 invalid evidence relationship: missing skill {skill_id} has claim links")
                refs = gap.claim_evidence[skill_id]
                ref_ids = [ref.mention_id for ref in refs]
                if len(ref_ids) != len(set(ref_ids)) or set(ref_ids) != set(mention_ids_for_skill):
                    raise ValueError(f"B2 invalid evidence relationship for skill {skill_id}: mention references disagree")
                for ref in refs:
                    mention = mention_by_id.get(ref.mention_id)
                    if mention is None:
                        raise ValueError(f"B2 invalid evidence relationship for skill {skill_id}: unknown mention {ref.mention_id}")
                    source_spans = mention.evidence_spans or [mention.text]
                    if not ref.evidence_spans or any(span not in source_spans for span in ref.evidence_spans):
                        raise ValueError(
                            f"B2 invalid evidence relationship for skill {skill_id}, mention {ref.mention_id}: "
                            "cited spans must be exact supplied CV evidence spans (or the claim text for claimed-only)"
                        )
                    if statuses.get(skill_id) == "matched_evidenced" and not mention.evidence_spans:
                        raise ValueError(
                            f"B2 invalid evidence relationship for skill {skill_id}, mention {ref.mention_id}: "
                            "matched_evidenced requires a supplied evidence span"
                        )
                    if statuses.get(skill_id) == "matched_claimed_only" and mention.evidence_spans:
                        raise ValueError(
                            f"B2 invalid evidence relationship for skill {skill_id}, mention {ref.mention_id}: "
                            "matched_claimed_only cannot cite a mention with evidence spans"
                        )
            if any(skill_id not in required for skill_id in gap.claim_evidence):
                raise ValueError("B2 evidence relationships contain an unsupported skill ID")
            for skill_id, status in statuses.items():
                mentions = gap.claim_matches.get(skill_id, [])
                if status == "missing" and mentions:
                    raise ValueError("B2 missing skills cannot have matched profile mentions")
                if status != "missing" and not mentions:
                    raise ValueError("B2 matched skill categories require supporting profile mentions")
                has_evidence = any(mention_by_id[m].evidence_spans for m in mentions)
                if status == "matched_evidenced" and not has_evidence:
                    raise ValueError("B2 matched_evidenced requires an evidence span")
                if status == "matched_claimed_only" and has_evidence:
                    raise ValueError("B2 matched_claimed_only cannot ignore supplied evidence spans")
        return BaselineInferenceResult(
            configuration_id=self.configuration_id,
            recommendations=recommendations,
            skill_gap=gap,
            roadmap=no_roadmap,
            verification=no_verification,
        )


class FrozenProfileBundleExtractor:
    """Extract the shared bundle once, without catalog lookup or persistence."""
    SYSTEM = """Extract only explicit information from the supplied CV text. Do not score or
recommend careers. Do not infer skills or proficiency. For each skill mention, provide a
short exact quoted evidence span from the supplied text.

Return exactly one JSON object with the keys below and no other keys. Use null when a value
is not stated. Never invent values.

- "skill_mentions": [{"text": str, "proficiency": str|null, "evidence_spans": [str]}]
- "experience": [{"company": str|null, "role_title": str, "employment_type": str|null,
  "start_date": str|null, "end_date": str|null, "description": str|null}]
- "education": [{"institution": str, "degree": str|null, "field_of_study": str|null,
  "start_date": str|null, "end_date": str|null, "description": str|null}]
- "projects": [{"title": str, "description": str|null, "url": str|null, "role": str|null}]
- "certifications": [{"name": str, "issuer": str|null, "issue_date": str|null,
  "expiry_date": str|null, "credential_url": str|null}]

Use these exact key names. For experience use "role_title", not "title"; for certifications
use "issue_date", not "date". Do not use a "dates" key. When the CV states a date range that
can be split into two stated values, put them in "start_date" and "end_date"; otherwise keep
the stated text verbatim in "description" and leave both date keys null. Put stated duties in
"description" as plain text rather than a separate list key.

Record proficiency only when stated explicitly. Do not return IDs, canonical labels,
ground-truth labels, or information not supported by the CV."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def run(self, extracted_cv_text: str) -> FrozenProfileBundle:
        redacted = redact_pii(extracted_cv_text).redacted_text
        raw = self.llm_client.complete_json(
            system=self.SYSTEM,
            user=f"REDACTED CV TEXT:\n{redacted}",
            max_tokens=8192,
        )
        mentions = raw.get("skill_mentions", []) if isinstance(raw, dict) else []
        if not isinstance(mentions, list):
            raise ValueError("profile extraction returned invalid skill_mentions")
        cleaned_mentions = []
        for index, item in enumerate(mentions, start=1):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise ValueError("profile extraction returned an invalid skill mention")
            spans = item.get("evidence_spans", [])
            if not isinstance(spans, list) or any(not isinstance(span, str) for span in spans):
                raise ValueError("profile extraction returned invalid evidence spans")
            cleaned_mentions.append(SkillMention(
                mention_id=f"m{index:04d}",
                text=item["text"],
                proficiency=item.get("proficiency"),
                evidence_spans=spans,
            ))
        experience = raw.get("experience", [])
        education = raw.get("education", [])
        projects = raw.get("projects", [])
        certifications = raw.get("certifications", [])
        if any(not isinstance(value, list) for value in (experience, education, projects, certifications)):
            raise ValueError("profile extraction returned invalid structured profile lists")
        return FrozenProfileBundle(
            extracted_cv_text=redacted,
            skill_mentions=cleaned_mentions,
            experience=experience,
            education=education,
            projects=projects,
            certifications=certifications,
        )
