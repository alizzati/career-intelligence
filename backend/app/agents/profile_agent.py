"""
Profile Agent (master prompt Section 5, Agent 1).

Responsibilities (and ONLY these -- this agent must NOT recommend careers):
  - parse a free-text user profile/CV
  - extract claimed skills, education, experience, projects, certifications
  - normalize each claimed skill against the KB (deterministic-first,
    LLM-assisted fallback, see skill_normalizer.py)
  - redact recognizable PII before the LLM and from extracted strings before
    returning or persisting the existing allowlisted profile fields
  - never upgrade a bare skill claim to a "verified" skill

Pipeline: PII redaction -> LLM extraction -> output redaction -> deterministic
normalization -> deterministic persistence. Only extraction touches the LLM. This module is
provider-agnostic: it depends only on the LLMClient Protocol (see
llm_client.py), never on a specific provider class or name.
"""
import json
from dataclasses import dataclass, field

import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

from app.agents.llm_client import LLMClient
from app.agents.skill_normalizer import normalize_skill, NormalizationResult, _norm
from app.services import evidence_acceptance_service as evidence_gate
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.services.pii_redaction_service import redact_pii, redact_structured_value

EXTRACTION_MAX_TOKENS = 8192
EXTRACTION_SYSTEM_PROMPT = """You are an information-extraction component in a career intelligence \
system. You extract structured facts from a candidate's free-text profile/CV. You do NOT evaluate, \
score, or recommend careers. You do NOT invent skills, employers, dates, or credentials that are not \
stated or clearly implied by the text. If something is not mentioned, omit it or leave it null -- never \
fabricate a plausible-sounding value.

You will also be given a catalog of canonical skill IDs from a knowledge base. For each claimed skill, \
if (and only if) you are confident it corresponds to one specific entry in that catalog, set \
candidate_skill_id to that entry's exact skill_id. If you are not confident, or no entry fits, set \
candidate_skill_id to null. NEVER invent a skill_id that is not literally present in the provided catalog.

Return ONLY a single JSON object, no prose, matching this schema exactly:
{
  "skills": [{"claimed_skill": str, "proficiency": str|null, "candidate_skill_id": str|null}],
  "evidence": [{"claimed_skill": str, "evidence_type": "education"|"project"|"work_experience"|
                "internship"|"certification"|"portfolio"|"github"|"self-report"|"other",
                "description": str, "evidence_span": str|null,
                "source_table": "user_education"|"user_experience"|"user_projects"|
                                "user_certifications"|null,
                "source_index": int|null, "url": str|null}],
  "education": [{"institution": str, "degree": str|null, "field_of_study": str|null,
                  "start_date": str|null, "end_date": str|null, "description": str|null}],
  "experience": [{"company": str, "role_title": str, "employment_type": str|null,
                   "start_date": str|null, "end_date": str|null, "description": str|null}],
  "projects": [{"title": str, "description": str|null, "url": str|null, "role": str|null}],
  "certifications": [{"name": str, "issuer": str|null, "issue_date": str|null,
                       "expiry_date": str|null, "credential_url": str|null,
                       "description": str|null}]
}

For every evidence item, evidence_span MUST be an exact contiguous quote copied from the candidate \
profile text (not a paraphrase). If no exact quote can be produced, set evidence_span to null. \
source_index is the 0-based position of the related item in the corresponding education/experience/ \
projects/certifications array. Never use a URL as the only evidence content."""


@dataclass
class SkillNormalizationReport:
    claimed_skill: str
    result: NormalizationResult
    mention_id: str | None = None


@dataclass
class ProfileAgentResult:
    user_id: int
    extracted: dict
    normalizations: list[SkillNormalizationReport] = field(default_factory=list)
    skills_persisted: int = 0
    evidence_persisted: int = 0
    evidence_candidates_persisted: int = 0
    evidence_accepted: int = 0
    evidence_revise: int = 0
    evidence_rejected: int = 0


class ProfileAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def _build_user_prompt(self, profile_text: str, skill_catalog: list[dict]) -> str:
        catalog_lines = "\n".join(f"{s['skill_id']}: {s['canonical_name']}" for s in skill_catalog)
        return (
            f"CANDIDATE PROFILE TEXT (PII redacted):\n---\n{profile_text}\n---\n\n"
            f"KNOWLEDGE-BASE SKILL CATALOG (skill_id: canonical_name):\n---\n{catalog_lines}\n---"
        )

    def run(self, user_id: int, raw_profile_text: str) -> ProfileAgentResult:
        profile_text = redact_pii(raw_profile_text).redacted_text
        skill_catalog = [s.model_dump() for s in rs.get_all_skills()]

        extracted = self.llm_client.complete_json(
            system=EXTRACTION_SYSTEM_PROMPT,
            user=self._build_user_prompt(profile_text, skill_catalog),
            max_tokens=EXTRACTION_MAX_TOKENS,
        )
        return self.persist_extracted(user_id, extracted, cv_text=profile_text)

    def run_from_bundle(self, user_id: int, bundle) -> ProfileAgentResult:
        """Normalize/persist the frozen extraction without re-running extraction."""
        value = bundle.model_dump() if hasattr(bundle, "model_dump") else dict(bundle)
        extracted = {
            "skills": [
                {"claimed_skill": row["text"], "candidate_skill_id": None,
                 "proficiency": row.get("proficiency"), "mention_id": row.get("mention_id")}
                for row in value.get("skill_mentions", [])
            ],
            "evidence": [
                {"claimed_skill": row["text"], "evidence_type": "other",
                 "description": span, "evidence_span": span, "url": None}
                for row in value.get("skill_mentions", [])
                for span in row.get("evidence_spans", [])
            ],
            "education": value.get("education", []),
            "experience": value.get("experience", []),
            "projects": value.get("projects", []),
            "certifications": value.get("certifications", []),
        }
        return self.persist_extracted(
            user_id, extracted, cv_text=value.get("extracted_cv_text"),
        )

    def persist_extracted(self, user_id: int, extracted: dict,
                          cv_text: str | None = None) -> ProfileAgentResult:
        """Apply the existing deterministic normalization and persistence stage."""
        extracted = redact_structured_value(extracted)
        skill_catalog = [s.model_dump() for s in rs.get_all_skills()]

        result = ProfileAgentResult(user_id=user_id, extracted=extracted)

        # --- persist education / experience / projects / certifications ---
        # (direct repository calls kept in user_service to stay consistent
        # with the existing Step 6 pattern; Profile Agent only orchestrates)
        source_rows: dict[str, list] = {
            "user_education": [], "user_experience": [],
            "user_projects": [], "user_certifications": [],
        }
        for edu in extracted.get("education", []):
            try:
                row = us.add_education(user_id, **_only(edu, [ "institution", "degree", "field_of_study",
                        "start_date", "end_date", "description" ])
                )
                source_rows["user_education"].append(row)
            except SQLAlchemyError as exc:
                logger.error( "Education database error: %s", str(getattr(exc, "orig", exc)))
                raise

        for exp in extracted.get("experience", []):
            row = us.add_experience(user_id, **_only(exp, ["company", "role_title", "employment_type",
                                                           "start_date", "end_date", "description"]))
            source_rows["user_experience"].append(row)
        for proj in extracted.get("projects", []):
            row = us.add_project(user_id, **_only(proj, ["title", "description", "url", "role"]))
            source_rows["user_projects"].append(row)
        for cert in extracted.get("certifications", []):
            row = us.add_certification(user_id, **_only(cert, ["name", "issuer", "issue_date",
                                                               "expiry_date", "credential_url"]))
            source_rows["user_certifications"].append(row)

        user_skill_ids_by_claim: dict[str, int] = {}
        normalizations_by_claim: dict[str, NormalizationResult] = {}
        for skill_claim in extracted.get("skills", []):
            claimed = skill_claim["claimed_skill"]
            norm = normalize_skill(
                claimed_skill=claimed,
                skill_catalog=skill_catalog,
                llm_suggested_skill_id=skill_claim.get("candidate_skill_id"),
            )
            normalizations_by_claim[_norm(claimed)] = norm
            result.normalizations.append(
                SkillNormalizationReport(claimed, norm, skill_claim.get("mention_id"))
            )

            us_row = us.add_user_skill(
                user_id=user_id,
                claimed_skill=claimed,                       # sanitized source value, never normalized
                skill_id=norm.skill_id,                       # None if unmatched -- NOT an error
                normalized_skill=norm.normalized_name,
                proficiency=skill_claim.get("proficiency"),
            )
            # internal matching key only -- NOT persisted, NOT the stored claimed_skill
            user_skill_ids_by_claim[_norm(claimed)] = us_row.user_skill_id
            result.skills_persisted += 1

        # --- evidence candidates + legacy audit rows ---
        # Candidate creation is intentionally non-fatal for profile persistence:
        # a failure here must not fabricate acceptance or discard the profile.
        try:
            cv_id = evidence_gate.cv_identity(user_id, cv_text)
            for ev in extracted.get("evidence", []):
                claimed = ev.get("claimed_skill")
                target_user_skill_id = (
                    user_skill_ids_by_claim.get(_norm(claimed)) if claimed else None
                )
                norm = (
                    normalizations_by_claim.get(_norm(claimed))
                    if claimed else None
                )
                if norm is None and claimed:
                    norm = normalize_skill(claimed_skill=claimed, skill_catalog=skill_catalog)
                skill_id = norm.skill_id if norm is not None else None
                source_type = (ev.get("evidence_type") or "other").strip().lower()
                source_table, source_id = _resolve_source(
                    ev, source_rows, user_id, target_user_skill_id,
                )
                evidence_text = ev.get("evidence_span") or ev.get("description")
                key = evidence_gate.candidate_key(
                    user_id, cv_id, source_table, source_id, skill_id, evidence_text,
                )
                us.create_evidence_candidate(
                    candidate_key=key, user_id=user_id, cv_id=cv_id,
                    source_type=source_type, source_table=source_table,
                    source_id=source_id, skill_id=skill_id,
                    claimed_skill=claimed, evidence_text=evidence_text,
                    evidence_span_hash=evidence_gate.span_hash(evidence_text),
                )
                result.evidence_candidates_persisted += 1
                result.evidence_persisted += 1

                # Legacy audit row only. mark_linked=False means it cannot
                # make the skill 'linked' in the effective profile.
                if target_user_skill_id is not None:
                    us.add_skill_evidence(
                        target_user_skill_id,
                        evidence_type=source_type,
                        source_table=source_table,
                        source_id=source_id,
                        description=evidence_text,
                        url=ev.get("url"),
                        mark_linked=False,
                    )

            summary = evidence_gate.evaluate_user_candidates(
                user_id, cv_text, self.llm_client,
            )
            result.evidence_accepted = summary["accepted"]
            result.evidence_revise = summary["revise"]
            result.evidence_rejected = summary["rejected"]
        except Exception as exc:
            # Database unavailable in an isolated context, or a source-row
            # problem. Never convert this into acceptance; report nothing.
            logger.warning(
                "Evidence acceptance pipeline did not complete (%s); no evidence was accepted.",
                type(exc).__name__,
            )

        return result



def _source_row_id(row, source_table: str) -> int | None:
    attribute = {
        "user_education": "education_id",
        "user_experience": "experience_id",
        "user_projects": "project_id",
        "user_certifications": "certification_id",
    }.get(source_table)
    return getattr(row, attribute, None) if attribute else None


_DEFAULT_SOURCE_BY_TYPE = {
    "project": "user_projects",
    "work_experience": "user_experience",
    "internship": "user_experience",
    "education": "user_education",
    "certification": "user_certifications",
}


def _resolve_source(ev: dict, source_rows: dict[str, list], user_id: int,
                    target_user_skill_id: int | None) -> tuple[str, int | None]:
    """Resolve a real, user-owned source row for a candidate.

    Explicit extractor metadata is preferred. Otherwise a unique source row of
    the matching type is used, then a normalized description match. When no
    activity source can be resolved, a claimed-skill row is the fallback; an
    evidence-only item with no source becomes ``user_profiles`` and will fail
    the structural source check if no profile row exists.
    """
    explicit_table = ev.get("source_table")
    explicit_index = ev.get("source_index")
    if explicit_table in source_rows and isinstance(explicit_index, int):
        rows = source_rows[explicit_table]
        if 0 <= explicit_index < len(rows):
            return explicit_table, _source_row_id(rows[explicit_index], explicit_table)

    evidence_type = (ev.get("evidence_type") or "").strip().lower()
    default_table = _DEFAULT_SOURCE_BY_TYPE.get(evidence_type)
    if default_table and source_rows.get(default_table):
        rows = source_rows[default_table]
        if len(rows) == 1:
            return default_table, _source_row_id(rows[0], default_table)
        wanted = _norm(ev.get("description") or ev.get("evidence_span") or "")
        if wanted:
            for row in rows:
                row_text = _norm(getattr(row, "description", None) or "")
                if row_text and (wanted in row_text or row_text in wanted):
                    return default_table, _source_row_id(row, default_table)

    if target_user_skill_id is not None:
        return "user_skills", target_user_skill_id
    return "user_profiles", user_id


def _only(d: dict, keys: list[str]) -> dict:
    return {k: d.get(k) for k in keys}
