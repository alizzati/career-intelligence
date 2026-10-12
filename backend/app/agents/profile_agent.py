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

from app.agents.llm_client import LLMClient
from app.agents.skill_normalizer import normalize_skill, NormalizationResult, _norm
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.services.pii_redaction_service import redact_pii, redact_structured_value


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
                "description": str, "url": str|null}],
  "education": [{"institution": str, "degree": str|null, "field_of_study": str|null,
                  "start_date": str|null, "end_date": str|null, "description": str|null}],
  "experience": [{"company": str, "role_title": str, "employment_type": str|null,
                   "start_date": str|null, "end_date": str|null, "description": str|null}],
  "projects": [{"title": str, "description": str|null, "url": str|null, "role": str|null}],
  "certifications": [{"name": str, "issuer": str|null, "issue_date": str|null,
                       "expiry_date": str|null, "credential_url": str|null}]
}"""


@dataclass
class SkillNormalizationReport:
    claimed_skill: str
    result: NormalizationResult


@dataclass
class ProfileAgentResult:
    user_id: int
    extracted: dict
    normalizations: list[SkillNormalizationReport] = field(default_factory=list)
    skills_persisted: int = 0
    evidence_persisted: int = 0


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
        )
        extracted = redact_structured_value(extracted)

        result = ProfileAgentResult(user_id=user_id, extracted=extracted)

        # --- persist education / experience / projects / certifications ---
        # (direct repository calls kept in user_service to stay consistent
        # with the existing Step 6 pattern; Profile Agent only orchestrates)
        for edu in extracted.get("education", []):
            us.add_education(user_id, **_only(edu, ["institution", "degree", "field_of_study",
                                                      "start_date", "end_date", "description"]))
        for exp in extracted.get("experience", []):
            us.add_experience(user_id, **_only(exp, ["company", "role_title", "employment_type",
                                                       "start_date", "end_date", "description"]))
        for proj in extracted.get("projects", []):
            us.add_project(user_id, **_only(proj, ["title", "description", "url", "role"]))
        for cert in extracted.get("certifications", []):
            us.add_certification(user_id, **_only(cert, ["name", "issuer", "issue_date",
                                                           "expiry_date", "credential_url"]))

        # --- normalize + persist sanitized skill claims regardless of match outcome ---
        #
        # *** B1 FIX ***
        # The lookup key used to re-associate evidence with a skill claim is
        # INTERNAL ONLY -- built via skill_normalizer._norm() (case/whitespace
        # -insensitive). This is matching-key normalization, not semantic
        # normalization: it does not use fuzzy similarity or the LLM, it only
        # makes "Database Management" / "database management" / "DATABASE
        # MANAGEMENT" collide as the same internal key so evidence attaches
        # correctly regardless of minor casing/whitespace differences across
        # the two LLM-produced JSON arrays. The stored `claimed_skill` column
        # is NEVER touched by this -- it stays exactly what was provided in
        # the already-redacted `skills[]` array. evidence_status is changed ONLY
        # by user_service.add_skill_evidence() actually persisting a row --
        # never inferred directly from LLM output.
        user_skill_ids_by_claim: dict[str, int] = {}
        for skill_claim in extracted.get("skills", []):
            claimed = skill_claim["claimed_skill"]
            norm = normalize_skill(
                claimed_skill=claimed,
                skill_catalog=skill_catalog,
                llm_suggested_skill_id=skill_claim.get("candidate_skill_id"),
            )
            result.normalizations.append(SkillNormalizationReport(claimed, norm))

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

        # --- attach evidence to the matching claimed skill, if any ---
        for ev in extracted.get("evidence", []):
            claimed = ev.get("claimed_skill")
            target_user_skill_id = user_skill_ids_by_claim.get(_norm(claimed)) if claimed else None
            if target_user_skill_id is None:
                # Evidence refers to a skill that was not in the "skills" list
                # extracted above (even after case/whitespace-insensitive
                # matching). Do not fabricate a user_skill row to hang it
                # on -- skip, rather than silently inventing a claim.
                continue
            us.add_skill_evidence(
                target_user_skill_id,
                evidence_type=ev["evidence_type"],
                description=ev.get("description"),
                url=ev.get("url"),
            )
            result.evidence_persisted += 1

        return result


def _only(d: dict, keys: list[str]) -> dict:
    return {k: d.get(k) for k in keys}