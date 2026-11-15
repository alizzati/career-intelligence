"""Stage 3.4.1 deterministic evidence-acceptance gate and semantic role.

Design invariants
-----------------
* Candidate evidence and accepted evidence are different states. Only this
  module moves a candidate into ``user_accepted_evidence``.
* Structural validation always runs first. A failed structural check can
  never be rescued by an LLM decision (D-01).
* The semantic LLM role only returns PASS / REVISE / FAIL plus a reason. It
  cannot write an accepted status or bypass the deterministic gate (D-03).
* LLM errors, unavailable clients, and malformed responses are treated as
  REVISE, never as PASS.
* One CV + one canonical skill contributes at most once. The repository
  enforces this with a unique key; duplicate candidates remain as audit rows
  but do not add credit (D-13/D-14/D-15).
* Raw CV spans are temporary. Terminal decisions clear the span immediately;
  REVISE retains it only until the bounded Evidence Gate recheck (B4).
"""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Literal

from app.core.db import engine
from app.repositories import user_repository as repo

CandidateStatus = Literal["pending", "accepted", "revise", "rejected"]
SemanticStatus = Literal["PASS", "REVISE", "FAIL", "not_attempted"]

ACCEPTANCE_PENDING = "pending"
ACCEPTANCE_ACCEPTED = "accepted"
ACCEPTANCE_REVISE = "revise"
ACCEPTANCE_REJECTED = "rejected"

STRUCTURAL_PENDING = "pending"
STRUCTURAL_PASSED = "passed"
STRUCTURAL_FAILED = "failed"

SEMANTIC_PASS = "PASS"
SEMANTIC_REVISE = "REVISE"
SEMANTIC_FAIL = "FAIL"
SEMANTIC_NOT_ATTEMPTED = "not_attempted"

ALLOWED_SOURCE_TABLES = {
    "user_education", "user_experience", "user_projects",
    "user_certifications", "user_profiles", "user_skills",
}

EVIDENCE_SEMANTIC_SYSTEM_PROMPT = """You are a separate evidence-verification role in a career \
intelligence system. You do NOT extract skills, you do NOT accept evidence, and you do NOT change \
any status. Your only job is to assess whether one supplied CV evidence passage supports one \
specified canonical skill.

Use only the supplied evidence passage and source-record metadata. Do not use outside knowledge, \
do not fetch URLs, and do not infer unrelated skills. A URL by itself is never sufficient evidence. \
A certification title or description may support a skill only when the skill is explicitly named \
or clearly entailed; broad or ambiguous certificate titles must not be expanded into unrelated \
skills. A bare skill list or self-assessment ("Skills: ...", "Familiar with ...") is not \
activity-based evidence.

Return exactly one JSON object with these keys and no prose:
{
  "decision": "PASS" | "REVISE" | "FAIL",
  "reason": "<short, factual explanation>",
  "skill_id": "<the exact supplied canonical skill_id>"
}

Use PASS only when the evidence describes an activity, deliverable, responsibility, project, \
education work, or certification content that demonstrates or clearly entails the named skill. A \
degree or institution name alone is not evidence of practical skill. \
Use REVISE when the evidence is ambiguous or insufficient. Use FAIL when the passage is a bare \
self-report, only a URL, or explicitly unrelated to the named skill."""

_SELF_REPORT_PATTERNS = (
    r"^\s*skills?\s*[:\-]",
    r"\bfamiliar with\b",
    r"\bknowledge of\b",
    r"\bproficient in\b",
    r"\bcomfortable with\b",
    r"\binterested in\b",
    r"\bcurrently learning\b",
    r"\bexposure to\b",
    r"\bself[-\s]?report",
    r"\bself[-\s]?assess",
)

_ACTIVITY_PATTERNS = (
    r"\bdeveloped\b", r"\bbuilt\b", r"\bdesigned\b", r"\bimplemented\b",
    r"\bcreated\b", r"\bdeployed\b", r"\banaly[sz]ed\b", r"\bautomated\b",
    r"\bmaintained\b", r"\bled\b", r"\bmanaged\b", r"\bdelivered\b",
    r"\bconducted\b", r"\bengineered\b", r"\bwrote\b", r"\bprogrammed\b",
    r"\bintegrated\b", r"\bmigrated\b", r"\btested\b", r"\bconfigured\b",
    r"\badministered\b", r"\bcompleted\b", r"\bproduced\b", r"\bused\b",
)

_URL_ONLY = re.compile(r"^\s*(?:https?://|www\.)\S+\s*$", re.IGNORECASE)


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def span_hash(value: str | None) -> str | None:
    normalized = normalize_text(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None


def cv_identity(user_id: int, cv_text: str | None) -> str:
    """Stable CV identity (D-14).

    When no source text is supplied the identity is intentionally unique:
    nothing can be structurally verified against an absent CV.
    """
    normalized = normalize_text(cv_text)
    if not normalized:
        return f"unverified-{uuid.uuid4().hex}"
    return hashlib.sha256(f"{user_id}:{normalized}".encode("utf-8")).hexdigest()[:32]


def candidate_key(user_id: int, cv_id: str, source_table: str,
                  source_id: int | None, skill_id: str | None,
                  evidence_text: str | None) -> str:
    parts = [
        str(user_id), cv_id, source_table, str(source_id), skill_id or "",
        span_hash(evidence_text) or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def classify_evidence_content(evidence_type: str | None, evidence_text: str | None,
                             claimed_skill: str | None = None) -> str:
    """Content-based self-report vs activity classification (D-06)."""
    text = normalize_text(evidence_text)
    label = (evidence_type or "").strip().lower()
    if any(re.search(pattern, text) for pattern in _SELF_REPORT_PATTERNS):
        return "self_report"
    # Extractors sometimes return only the skill phrase itself (or a bare
    # comma-separated skill list) as the evidence span. Detect that from the
    # content and the associated claim; never use the extractor's type label
    # as the sole basis for classifying a passage.
    claim = normalize_text(claimed_skill)
    if claim and text:
        claim_items = {
            normalize_text(item).strip(" .-*\t")
            for item in re.split(r"[,;|\n]", text)
        }
        if text == claim or claim in claim_items:
            return "self_report"
    if label == "certification":
        return "certification"
    if any(re.search(pattern, text) for pattern in _ACTIVITY_PATTERNS):
        return "activity"
    # Source labels provide routing context, not proof that the passage
    # describes activity. Ambiguous content must be semantically assessed.
    return "ambiguous"


def _source_text(candidate: dict, source_record: dict | None) -> str | None:
    if source_record is None:
        return None
    for field in ("description", "summary", "headline", "name", "claimed_skill"):
        value = source_record.get(field)
        if value:
            return value
    return None


def _certification_title(source_record: dict | None) -> str | None:
    if source_record is None:
        return None
    title = (source_record.get("name") or "").strip()
    return title or None


def _mentions_skill(canonical_name: str, text: str | None) -> bool:
    name = normalize_text(canonical_name)
    haystack = normalize_text(text)
    if not name or not haystack:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _structural_check(conn, candidate: dict, cv_text: str | None) -> tuple[bool, str]:
    """Return (passed, reason). Mandatory before any semantic assessment."""
    skill_id = candidate.get("skill_id")
    if not skill_id:
        return False, "Candidate has no valid canonical skill_id."
    if repo.fetch_skill_name(conn, skill_id) is None:
        return False, "Canonical skill_id does not exist in the knowledge base."

    source_table = candidate.get("source_table")
    source_id = candidate.get("source_id")
    if source_table not in ALLOWED_SOURCE_TABLES:
        return False, "Candidate source_type is not an allowed source record."
    if source_id is None:
        return False, "Candidate has no source record identity."

    source_record = repo.fetch_evidence_source_record(
        conn, source_table, source_id, candidate["user_id"],
    )
    if source_record is None:
        return False, "Source record does not exist or does not belong to this user."

    if source_table == "user_certifications" and not _certification_title(source_record):
        return False, "Certification title is missing (required by D-09)."

    evidence_text = (candidate.get("evidence_text") or "").strip()
    if not evidence_text:
        return False, "Candidate has no evidence text to verify against the CV."
    if _URL_ONLY.match(evidence_text):
        return False, "A URL alone is not sufficient evidence (D-07)."

    normalized_cv = normalize_text(cv_text)
    if not normalized_cv:
        return False, "No supplied CV source content is available for span verification."
    if normalize_text(evidence_text) not in normalized_cv:
        return False, "Evidence text is not traceable to the supplied CV source."

    return True, "Source record exists, belongs to the user, and the evidence text is present in the CV."


def _deterministic_anchor(candidate: dict, canonical_name: str | None,
                          source_record: dict | None) -> tuple[str, str] | None:
    """Deterministic PASS only for clearly supported certification cases."""
    if candidate.get("source_type") != "certification" or not canonical_name:
        return None
    if candidate.get("source_table") != "user_certifications":
        return None
    title = _certification_title(source_record)
    if _mentions_skill(canonical_name, title):
        return SEMANTIC_PASS, "Deterministic certification anchor: the certificate title clearly names the skill."
    return None


def _semantic_assess(llm_client, candidate: dict, canonical_name: str | None,
                     source_record: dict | None) -> tuple[str, str]:
    if llm_client is None:
        return SEMANTIC_REVISE, "No LLM verification client is available; not treated as PASS."
    evidence_text = candidate.get("evidence_text") or ""
    source_text = _source_text(candidate, source_record) or ""
    user_prompt = (
        f"Canonical skill: {canonical_name or ''} ({candidate.get('skill_id')})\n"
        f"Evidence type: {candidate.get('source_type')}\n"
        f"Source record text: {source_text}\n"
        f"CV evidence passage:\n---\n{evidence_text}\n---"
    )
    try:
        response = llm_client.complete_json(
            system=EVIDENCE_SEMANTIC_SYSTEM_PROMPT, user=user_prompt, max_tokens=400,
        )
        if not isinstance(response, dict) or set(response) != {"decision", "reason", "skill_id"}:
            raise ValueError("semantic response must contain exactly decision, reason, and skill_id")
        decision = response["decision"]
        reason = response["reason"]
        matched_skill_id = response["skill_id"]
        if decision not in {SEMANTIC_PASS, SEMANTIC_REVISE, SEMANTIC_FAIL}:
            raise ValueError("semantic decision is not PASS, REVISE, or FAIL")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("semantic reason must be a non-empty string")
        if matched_skill_id != candidate.get("skill_id"):
            raise ValueError("semantic response names a different skill_id")
        return decision, reason.strip()[:500]
    except Exception as exc:  # provider errors and malformed output are not PASS
        return (
            SEMANTIC_REVISE,
            f"Semantic verification unavailable or malformed; not treated as PASS "
            f"({type(exc).__name__}).",
        )


def _apply_decision(conn, candidate: dict, *, structural_status: str,
                    structural_reason: str, semantic_status: str,
                    decision_reason: str, canonical_name: str | None,
                    clear_span: bool = True) -> dict:
    candidate_id = candidate["candidate_id"]
    accepted_row = None
    accepted_created = False
    if semantic_status == SEMANTIC_PASS and structural_status == STRUCTURAL_PASSED:
        accepted_row, accepted_created = repo.insert_accepted_evidence(
            conn,
            user_id=candidate["user_id"], cv_id=candidate["cv_id"],
            skill_id=candidate["skill_id"], candidate_id=candidate_id,
            source_type=candidate["source_type"],
            source_table=candidate["source_table"],
            source_id=candidate.get("source_id"),
            claimed_skill=candidate.get("claimed_skill"),
        )
        acceptance_status = ACCEPTANCE_ACCEPTED
        if not accepted_created:
            decision_reason = (
                f"{decision_reason} Duplicate contribution suppressed: accepted evidence "
                f"already exists for this CV and canonical skill."
            )
    elif semantic_status == SEMANTIC_REVISE:
        acceptance_status = ACCEPTANCE_REVISE
    else:
        acceptance_status = ACCEPTANCE_REJECTED

    updated = repo.update_evidence_candidate(
        conn, candidate_id,
        structural_status=structural_status,
        structural_reason=structural_reason,
        semantic_status=semantic_status,
        decision_reason=decision_reason,
        acceptance_status=acceptance_status,
    )
    # Keep a REVISE span only until the bounded evidence-gate recheck. The
    # caller clears it after that lifecycle completes; terminal decisions
    # discard it immediately.
    if clear_span:
        repo.clear_evidence_candidate_span(conn, candidate_id)
    return {
        "candidate_id": candidate_id,
        "acceptance_status": acceptance_status,
        "semantic_status": semantic_status,
        "decision_reason": decision_reason,
        "accepted_evidence": accepted_row,
        "accepted_created": accepted_created,
        "canonical_name": canonical_name,
        "candidate": updated,
    }


def evaluate_candidate(candidate_id: int, cv_text: str | None, llm_client=None) -> dict | None:
    """Run the deterministic gate for one candidate and persist its decision."""
    with engine.begin() as conn:
        candidate = repo.fetch_evidence_candidate(conn, candidate_id)
        if candidate is None:
            return None

        passed, structural_reason = _structural_check(conn, candidate, cv_text)
        if not passed:
            return _apply_decision(
                conn, candidate, structural_status=STRUCTURAL_FAILED,
                structural_reason=structural_reason,
                semantic_status=SEMANTIC_NOT_ATTEMPTED,
                decision_reason=structural_reason,
                canonical_name=None,
            )

        canonical_name = repo.fetch_skill_name(conn, candidate["skill_id"])
        source_record = repo.fetch_evidence_source_record(
            conn, candidate["source_table"], candidate["source_id"], candidate["user_id"],
        )
        anchor = _deterministic_anchor(candidate, canonical_name, source_record)
        if anchor is not None:
            semantic_status, reason = anchor
            return _apply_decision(
                conn, candidate, structural_status=STRUCTURAL_PASSED,
                structural_reason=structural_reason,
                semantic_status=semantic_status, decision_reason=reason,
                canonical_name=canonical_name,
            )

        content_class = classify_evidence_content(
            candidate.get("source_type"), candidate.get("evidence_text"),
            candidate.get("claimed_skill"),
        )
        if content_class == "self_report":
            reason = "Self-report or skill list alone cannot become accepted evidence (D-06)."
            return _apply_decision(
                conn, candidate, structural_status=STRUCTURAL_PASSED,
                structural_reason=structural_reason,
                semantic_status=SEMANTIC_FAIL, decision_reason=reason,
                canonical_name=canonical_name,
            )

        if content_class == "certification":
            # The deterministic title anchor above handles explicit names;
            # unresolved title/description relationships go to the separate
            # semantic verifier and cannot be guessed from the certificate label.
            semantic_status, reason = _semantic_assess(
                llm_client, candidate, canonical_name, source_record,
            )
        else:
            semantic_status, reason = _semantic_assess(
                llm_client, candidate, canonical_name, source_record,
            )

        return _apply_decision(
            conn, candidate, structural_status=STRUCTURAL_PASSED,
            structural_reason=structural_reason,
            semantic_status=semantic_status, decision_reason=reason,
            canonical_name=canonical_name,
            clear_span=(semantic_status != SEMANTIC_REVISE),
        )


def evaluate_user_candidates(user_id: int, cv_text: str | None, llm_client=None,
                             max_candidates: int | None = None) -> dict:
    """Evaluate every pending candidate for one user/CV submission."""
    with engine.connect() as conn:
        pending = repo.fetch_evidence_candidates(conn, user_id, ACCEPTANCE_PENDING)
    if max_candidates is not None:
        pending = pending[:max_candidates]
    summary = {
        "evaluated": 0, "accepted": 0, "revise": 0, "rejected": 0,
        "duplicate_suppressed": 0,
    }
    for candidate in pending:
        result = evaluate_candidate(candidate["candidate_id"], cv_text, llm_client)
        if result is None:
            continue
        summary["evaluated"] += 1
        status = result["acceptance_status"]
        if status == ACCEPTANCE_ACCEPTED:
            summary["accepted"] += 1
            if not result.get("accepted_created", False):
                summary["duplicate_suppressed"] += 1
        elif status == ACCEPTANCE_REVISE:
            summary["revise"] += 1
        else:
            summary["rejected"] += 1
    return summary


def reassess_revise_candidates(user_id: int, llm_client=None) -> dict:
    """Re-run the semantic gate for structurally valid REVISE candidates.

    A REVISE candidate retains its raw span only until this bounded recheck.
    The source owner and record are revalidated; the span hash must still match
    the originally CV-verified span before semantic reassessment.
    """
    with engine.connect() as conn:
        candidates = [
            row for row in repo.fetch_evidence_candidates(conn, user_id)
            if row["acceptance_status"] in {ACCEPTANCE_REVISE, ACCEPTANCE_PENDING}
            and row["structural_status"] == STRUCTURAL_PASSED
        ]
    summary = {"reassessed": 0, "accepted": 0, "revise": 0, "rejected": 0}
    for candidate in candidates:
        with engine.begin() as conn:
            fresh = repo.fetch_evidence_candidate(conn, candidate["candidate_id"])
            if fresh is None:
                continue
            source_record = repo.fetch_evidence_source_record(
                conn, fresh["source_table"], fresh["source_id"], fresh["user_id"],
            )
            evidence_text = fresh.get("evidence_text")
            if (source_record is None or not evidence_text
                    or span_hash(evidence_text) != fresh.get("evidence_span_hash")):
                result = _apply_decision(
                    conn, fresh, structural_status=STRUCTURAL_FAILED,
                    structural_reason="REVISE recheck failed: source record or verified span is unavailable.",
                    semantic_status=SEMANTIC_NOT_ATTEMPTED,
                    decision_reason="Evidence was not reaccepted because its verified source could not be rechecked.",
                    canonical_name=None,
                )
                summary["reassessed"] += 1
                summary["rejected"] += 1
                continue
            canonical_name = repo.fetch_skill_name(conn, fresh["skill_id"])
            anchor = _deterministic_anchor(fresh, canonical_name, source_record)
            if anchor is not None:
                semantic_status, reason = anchor
                result = _apply_decision(
                    conn, fresh, structural_status=STRUCTURAL_PASSED,
                    structural_reason=fresh.get("structural_reason") or "Structurally validated.",
                    semantic_status=semantic_status, decision_reason=reason,
                    canonical_name=canonical_name,
                )
                summary["reassessed"] += 1
                if result["acceptance_status"] == ACCEPTANCE_ACCEPTED:
                    summary["accepted"] += 1
                else:
                    summary["rejected"] += 1
                continue
            content_class = classify_evidence_content(
                fresh.get("source_type"), evidence_text, fresh.get("claimed_skill"),
            )
            if content_class == "self_report":
                result = _apply_decision(
                    conn, fresh, structural_status=STRUCTURAL_PASSED,
                    structural_reason=fresh.get("structural_reason") or "Structurally validated.",
                    semantic_status=SEMANTIC_FAIL,
                    decision_reason="Self-report or skill list alone cannot become accepted evidence (D-06).",
                    canonical_name=canonical_name,
                )
            else:
                semantic_status, reason = _semantic_assess(
                    llm_client, fresh, canonical_name, source_record,
                )
                result = _apply_decision(
                    conn, fresh, structural_status=STRUCTURAL_PASSED,
                    structural_reason=fresh.get("structural_reason") or "Structurally validated.",
                    semantic_status=semantic_status, decision_reason=reason,
                    canonical_name=canonical_name,
                )
        summary["reassessed"] += 1
        status = result["acceptance_status"]
        if status == ACCEPTANCE_ACCEPTED:
            summary["accepted"] += 1
        elif status == ACCEPTANCE_REVISE:
            summary["revise"] += 1
        else:
            summary["rejected"] += 1
    return summary


def discard_revise_spans(user_id: int) -> int:
    """Clear temporary spans when the workflow has no revision budget left."""
    with engine.begin() as conn:
        return repo.clear_revise_evidence_spans(conn, user_id)


class EvidenceGate:
    """Revision-workflow adapter for rechecking evidence candidates."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def reassess_user_evidence(self, user_id: int) -> dict:
        return reassess_revise_candidates(user_id, self.llm_client)

    def discard_revise_spans(self, user_id: int) -> int:
        return discard_revise_spans(user_id)
