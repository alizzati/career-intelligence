"""
Grounding guard for the Skill-Gap Agent (Step 10).

Pure module: no database, no LLM, no network. It does two things:

  1. build_fallback_narrative(gap): a deterministic narrative written ONLY
     from the Step 9 result (used when no LLM is configured, when the LLM
     fails, or to replace LLM parts that fail validation).
  2. validate_narrative(raw, gap, vocabulary): checks an LLM-produced
     narrative against the Step 9 result and drops (never repairs) any part
     that is not grounded in it.

What "grounded" means here (all deterministic, none relies on the prompt):
  * Structure: every observation carries ids (skill_ids / user_skill_ids)
    that must belong to the matching category of the Step 9 result.
  * Vocabulary: any KB skill name, KB career name, or KB technology name
    found in the text must be part of the supplied context for that item.
    Names from a DIFFERENT category (e.g. a missing skill named inside a
    strengths item) are rejected too.
  * Numbers: the only percentage allowed is the deterministic fit score.
  * Concepts: no priority / severity / tier / required-proficiency language.
  * Wording: claimed-only text may not assert demonstrated/verified skill;
    evidenced text may not call a skill unverified; unmatched-claim text may
    not call a claim missing/absent.

Known limits (documented, not hidden): a term that is in NONE of the KB
vocabularies cannot be recognized by string matching, and wrong counts in
prose are not checked. That residual risk is why the structured ids are the
primary guard and why Step 12 (Verification Agent) exists.
"""
import re
from dataclasses import dataclass, field

from app.schemas.skill_gap import SkillGapResult
from app.schemas.skill_gap_agent import (
    SkillGapNarrative, SkillObservation, UnmatchedClaimObservation,
)

# Category labels (shared by terms and items)
LABEL_EVIDENCED = "matched_evidenced"
LABEL_CLAIMED_ONLY = "matched_claimed_only"
LABEL_MISSING = "missing"
LABEL_UNMATCHED = "unmatched"
NEUTRAL = "neutral"          # career name / domain: allowed anywhere
UNGROUNDED = "ungrounded"    # known to the KB but NOT part of the supplied context

MAX_TEXT_CHARS = 1500
PERCENT_TOLERANCE = 0.5      # percentage points around the deterministic fit score

KNOWN_KEYS = ("summary", "strengths", "claimed_only_observations",
              "missing_skill_observations", "unmatched_claim_observations", "conclusion")


class NarrativeFormatError(ValueError):
    """The LLM output is not a usable narrative object at all."""


@dataclass(frozen=True)
class Vocabulary:
    """KB names used ONLY to recognize ungrounded mentions in LLM text."""
    skill_names: tuple[str, ...] = ()
    technology_names: tuple[str, ...] = ()
    career_names: tuple[str, ...] = ()


@dataclass
class ValidationOutcome:
    narrative: SkillGapNarrative
    notes: list[str] = field(default_factory=list)
    degraded: bool = False     # True if anything was dropped or replaced


# --------------------------------------------------------------------------
# Deterministic fallback narrative
# --------------------------------------------------------------------------

def _names(items) -> str:
    return ", ".join(i.canonical_name for i in items)


def build_fallback_narrative(gap: SkillGapResult) -> SkillGapNarrative:
    n_req = len(gap.matched_evidenced) + len(gap.matched_claimed_only) + len(gap.missing)
    pct = f"{gap.fit_score * 100:.1f}%"

    summary = (
        f"{gap.canonical_name} ({gap.domain}): deterministic comparison of the user's profile with "
        f"{n_req} required skill(s). Matched with linked evidence: {len(gap.matched_evidenced)}. "
        f"Claimed without linked evidence: {len(gap.matched_claimed_only)}. "
        f"No corresponding canonical skill in the profile: {len(gap.missing)}. Career-fit score: {pct}."
    )
    strengths = [SkillObservation(
        skill_ids=[i.skill_id for i in gap.matched_evidenced],
        text=f"Required skills matched with linked evidence: {_names(gap.matched_evidenced)}.",
    )] if gap.matched_evidenced else []
    claimed = [SkillObservation(
        skill_ids=[i.skill_id for i in gap.matched_claimed_only],
        text=(f"Required skills the user claims but that have no linked evidence yet: "
              f"{_names(gap.matched_claimed_only)}. These are reported by the user and not yet supported by linked evidence."),
    )] if gap.matched_claimed_only else []
    missing = [SkillObservation(
        skill_ids=[i.skill_id for i in gap.missing],
        text=f"Required by this career but with no corresponding canonical skill in the user's profile: {_names(gap.missing)}.",
    )] if gap.missing else []
    unmatched = [UnmatchedClaimObservation(
        user_skill_ids=[u.user_skill_id for u in gap.unmatched_user_claims],
        text=("User claims that could not be mapped to a canonical KB skill: "
              + ", ".join(f"'{u.claimed_skill}'" for u in gap.unmatched_user_claims)
              + ". They were not evaluated against this career's requirements and do not count as unmet "
                "requirements; they are not evidence that the user does not have these skills."),
    )] if gap.unmatched_user_claims else []
    conclusion = (
        "This explanation restates the deterministic classification and does not add requirements or change "
        "any classification. Claimed skills still need linked evidence, and user claims outside the knowledge "
        "base were not part of the comparison."
    )
    return SkillGapNarrative(
        summary=summary, strengths=strengths, claimed_only_observations=claimed,
        missing_skill_observations=missing, unmatched_claim_observations=unmatched, conclusion=conclusion,
    )


# --------------------------------------------------------------------------
# Text checks
# --------------------------------------------------------------------------

_CONCEPT_PATTERNS = [
    (re.compile(r"priorit", re.I), "priority/prioritization language"),
    (re.compile(r"\bseverity\b", re.I), "severity language"),
    (re.compile(r"\btiers?\b", re.I), "tier language"),
    (re.compile(r"\burgen", re.I), "urgency language"),
    (re.compile(r"\bmost (?:important|critical)\b", re.I), "ranking language"),
    (re.compile(r"\b(?:required|target)\s+(?:proficiency|level)\b", re.I), "required-proficiency language"),
    (re.compile(r"\bproficiency\s+(?:requirement|threshold|gap|deficit)s?\b", re.I), "proficiency-requirement language"),
    (re.compile(r"\b(?:requires?|needs?|must reach|should reach)\s+(?:an?\s+)?(?:beginner|intermediate|advanced|expert)\b", re.I),
     "required-proficiency language"),
    (re.compile(r"\b(?:beginner|intermediate|advanced|expert)[- ]level\s+(?:is\s+)?(?:required|needed|expected)\b", re.I),
     "required-proficiency language"),
]
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_NEGATORS = re.compile(r"\b(?:not|no|never|without|neither|nor|cannot|yet)\b|n't", re.I)

_EVIDENCE_ASSERTIONS = ("demonstrated", "demonstrates", "proven", "proved", "verified", "confirmed", "validated", "established")
_ABSENCE_ASSERTIONS = ("missing", "lacks", "lacking", "absent")
_UNVERIFIED_PHRASES = ("claimed only", "claim-only", "claim only", "only claimed", "unverified",
                       "not yet supported", "no linked evidence", "without evidence", "no evidence")


def _affirmative_hits(text: str, words) -> list[str]:
    """Words from `words` present in `text` WITHOUT a negator in the 40 chars before them
    ('not yet verified' is fine, 'is verified' is not)."""
    hits = []
    for w in words:
        for m in re.finditer(r"\b" + re.escape(w) + r"\b", text, re.I):
            window = text[max(0, m.start() - 40):m.start()]
            if not _NEGATORS.search(window):
                hits.append(w)
                break
    return hits


def _word_re(text: str, ignore_case: bool) -> re.Pattern:
    body = r"\s+".join(re.escape(tok) for tok in text.split())
    return re.compile(r"(?<![A-Za-z0-9_])" + body + r"(?![A-Za-z0-9_])", re.I if ignore_case else 0)


def _tech_aliases(name: str) -> list[str]:
    """The KB name plus two conservative aliases: an ALL-CAPS token such as 'AWS' in
    'Amazon Web Services AWS', and the name without that trailing token."""
    aliases = [name]
    tokens = name.split()
    caps = [t for t in tokens if t.isalpha() and t.isupper() and len(t) >= 3]
    aliases.extend(caps)
    if len(tokens) >= 2 and tokens[-1] in caps:
        aliases.append(" ".join(tokens[:-1]))
    return aliases


@dataclass
class _Term:
    text: str
    regex: re.Pattern
    labels: frozenset


class _Context:
    """Everything a text may legitimately mention, labeled by category."""

    def __init__(self, gap: SkillGapResult, vocab: Vocabulary):
        self.gap = gap
        self.fit_pct = gap.fit_score * 100

        grounded: dict[str, tuple[str, set]] = {}

        def add(text, label):
            t = (text or "").strip()
            if len(t) >= 2:
                grounded.setdefault(t.lower(), (t, set()))[1].add(label)

        add(gap.canonical_name, NEUTRAL)
        add(gap.domain, NEUTRAL)
        for label, items in ((LABEL_EVIDENCED, gap.matched_evidenced),
                             (LABEL_CLAIMED_ONLY, gap.matched_claimed_only),
                             (LABEL_MISSING, gap.missing)):
            for it in items:
                add(it.canonical_name, label)
                if it.matched_user_claim:
                    add(it.matched_user_claim.claimed_skill, label)
        for u in gap.unmatched_user_claims:
            add(u.claimed_skill, LABEL_UNMATCHED)

        self.terms: list[_Term] = [
            _Term(t, _word_re(t, True), frozenset(labels)) for t, labels in grounded.values()
        ]
        known = set(grounded)
        for name in tuple(vocab.skill_names) + tuple(vocab.career_names):
            n = name.strip()
            if len(n) >= 2 and n.lower() not in known:
                known.add(n.lower())
                self.terms.append(_Term(n, _word_re(n, True), frozenset({UNGROUNDED})))
        seen_tech: set[str] = set()
        for name in vocab.technology_names:
            for alias in _tech_aliases(name.strip()):
                if (len(alias) < 3 and alias.isalpha()) or alias in seen_tech or alias.lower() in known:
                    continue
                seen_tech.add(alias)
                self.terms.append(_Term(alias, _word_re(alias, False), frozenset({UNGROUNDED})))

    def scan_terms(self, text: str, item_label) -> list[str]:
        """Longest-match-first, non-overlapping scan so that e.g. 'Database' inside
        'Database Management' is never read as a separate (ungrounded) mention."""
        candidates = []
        for term in self.terms:
            for m in term.regex.finditer(text):
                candidates.append((m.start(), m.end(), term))
        candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
        accepted: list[tuple[int, int, _Term]] = []
        for s, e, term in candidates:
            if any(s < ae and a_s < e for a_s, ae, _ in accepted):
                continue
            accepted.append((s, e, term))
        problems: list[str] = []
        for s, e, term in sorted(accepted, key=lambda a: a[0]):
            shown = text[s:e]
            if UNGROUNDED in term.labels:
                msg = f"mentions '{shown}', which is not part of the supplied deterministic context"
            elif NEUTRAL in term.labels or item_label is None or item_label in term.labels:
                continue
            else:
                msg = (f"mentions '{shown}', which belongs to a different category "
                       f"({'/'.join(sorted(term.labels))}) than this item ({item_label})")
            if msg not in problems:
                problems.append(msg)
        return problems


def _text_problems(text, ctx: _Context, item_label) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return ["text is empty or not a string"]
    problems = []
    if len(text) > MAX_TEXT_CHARS:
        problems.append(f"text longer than {MAX_TEXT_CHARS} characters")
    for pattern, label in _CONCEPT_PATTERNS:
        if pattern.search(text):
            problems.append(f"contains {label}")
    for m in _PERCENT.finditer(text):
        value = float(m.group(1).replace(",", "."))
        if abs(value - ctx.fit_pct) > PERCENT_TOLERANCE:
            problems.append(f"contains the percentage {m.group(0).strip()} which is not the deterministic "
                            f"fit score ({ctx.fit_pct:.1f}%)")
    problems.extend(ctx.scan_terms(text, item_label))

    if item_label in (LABEL_CLAIMED_ONLY, LABEL_MISSING):
        hits = _affirmative_hits(text, _EVIDENCE_ASSERTIONS)
        if hits:
            problems.append(f"asserts evidence ({', '.join(hits)}) for skills without linked evidence")
    elif item_label == LABEL_EVIDENCED:
        hits = [p for p in _UNVERIFIED_PHRASES if p in text.lower()]
        if hits:
            problems.append(f"describes an evidenced skill as unverified ({', '.join(hits)})")
    elif item_label == LABEL_UNMATCHED:
        hits = _affirmative_hits(text, _ABSENCE_ASSERTIONS)
        if hits:
            problems.append(f"treats an unmapped claim as absent/missing ({', '.join(hits)})")
    return problems


# --------------------------------------------------------------------------
# Validation of an LLM narrative
# --------------------------------------------------------------------------

def _validate_skill_items(raw_list, field_name, label, allowed_ids, ctx, notes) -> list[SkillObservation]:
    kept: list[SkillObservation] = []
    if raw_list is None:
        return kept
    if not isinstance(raw_list, list):
        notes.append(f"dropped {field_name}: not a list")
        return kept
    for idx, raw in enumerate(raw_list):
        where = f"{field_name}[{idx}]"
        if not isinstance(raw, dict):
            notes.append(f"dropped {where}: not an object")
            continue
        ids, text = raw.get("skill_ids"), raw.get("text")
        if not (isinstance(ids, list) and ids and all(isinstance(i, str) for i in ids)):
            notes.append(f"dropped {where}: skill_ids must be a non-empty list of strings")
            continue
        bad = [i for i in ids if i not in allowed_ids]
        if bad:
            notes.append(f"dropped {where}: skill_ids {bad} are not in the '{label}' category of the deterministic result")
            continue
        problems = _text_problems(text, ctx, label)
        if problems:
            notes.append(f"dropped {where}: " + "; ".join(problems))
            continue
        kept.append(SkillObservation(skill_ids=list(dict.fromkeys(ids)), text=text.strip()))
    return kept


def _validate_unmatched_items(raw_list, field_name, allowed_ids, ctx, notes) -> list[UnmatchedClaimObservation]:
    kept: list[UnmatchedClaimObservation] = []
    if raw_list is None:
        return kept
    if not isinstance(raw_list, list):
        notes.append(f"dropped {field_name}: not a list")
        return kept
    for idx, raw in enumerate(raw_list):
        where = f"{field_name}[{idx}]"
        if not isinstance(raw, dict):
            notes.append(f"dropped {where}: not an object")
            continue
        ids, text = raw.get("user_skill_ids"), raw.get("text")
        if not (isinstance(ids, list) and ids and all(isinstance(i, int) and not isinstance(i, bool) for i in ids)):
            notes.append(f"dropped {where}: user_skill_ids must be a non-empty list of integers")
            continue
        bad = [i for i in ids if i not in allowed_ids]
        if bad:
            notes.append(f"dropped {where}: user_skill_ids {bad} are not unmatched claims in the deterministic result")
            continue
        problems = _text_problems(text, ctx, LABEL_UNMATCHED)
        if problems:
            notes.append(f"dropped {where}: " + "; ".join(problems))
            continue
        kept.append(UnmatchedClaimObservation(user_skill_ids=list(dict.fromkeys(ids)), text=text.strip()))
    return kept


def validate_narrative(raw, gap: SkillGapResult, vocab: Vocabulary) -> ValidationOutcome:
    """
    Never modifies `gap`. Drops invalid parts and fills them from the
    deterministic template; never edits LLM text to 'repair' it.
    Raises NarrativeFormatError only if `raw` is not a usable narrative object.
    """
    if not isinstance(raw, dict):
        raise NarrativeFormatError(f"LLM output is not a JSON object (got {type(raw).__name__})")
    if not any(k in raw for k in KNOWN_KEYS):
        raise NarrativeFormatError("LLM output contains none of the expected narrative fields")

    ctx = _Context(gap, vocab)
    fallback = build_fallback_narrative(gap)
    notes: list[str] = []
    degraded = False

    for key in raw:
        if key not in KNOWN_KEYS:
            notes.append(f"ignored unexpected key {key!r} (the deterministic result cannot be changed by the LLM)")

    def free_text(field_name, fallback_text):
        nonlocal degraded
        value = raw.get(field_name)
        problems = _text_problems(value, ctx, None)
        if problems:
            notes.append(f"replaced {field_name} with the deterministic template: " + "; ".join(problems))
            degraded = True
            return fallback_text
        return value.strip()

    summary = free_text("summary", fallback.summary)
    conclusion = free_text("conclusion", fallback.conclusion)

    n_before = len(notes)
    strengths = _validate_skill_items(raw.get("strengths"), "strengths", LABEL_EVIDENCED,
                                      {i.skill_id for i in gap.matched_evidenced}, ctx, notes)
    claimed = _validate_skill_items(raw.get("claimed_only_observations"), "claimed_only_observations",
                                    LABEL_CLAIMED_ONLY, {i.skill_id for i in gap.matched_claimed_only}, ctx, notes)
    missing = _validate_skill_items(raw.get("missing_skill_observations"), "missing_skill_observations",
                                    LABEL_MISSING, {i.skill_id for i in gap.missing}, ctx, notes)
    unmatched = _validate_unmatched_items(raw.get("unmatched_claim_observations"), "unmatched_claim_observations",
                                          {u.user_skill_id for u in gap.unmatched_user_claims}, ctx, notes)
    if len(notes) > n_before:
        degraded = True

    # A non-empty category must still be explained: use the template if no LLM item survived.
    for name, kept, template, category_has_items in (
        ("strengths", strengths, fallback.strengths, bool(gap.matched_evidenced)),
        ("claimed_only_observations", claimed, fallback.claimed_only_observations, bool(gap.matched_claimed_only)),
        ("missing_skill_observations", missing, fallback.missing_skill_observations, bool(gap.missing)),
        ("unmatched_claim_observations", unmatched, fallback.unmatched_claim_observations, bool(gap.unmatched_user_claims)),
    ):
        if category_has_items and not kept:
            kept.extend(template)
            notes.append(f"{name}: no valid LLM item survived; deterministic template used")
            degraded = True

    narrative = SkillGapNarrative(
        summary=summary, strengths=strengths, claimed_only_observations=claimed,
        missing_skill_observations=missing, unmatched_claim_observations=unmatched, conclusion=conclusion,
    )
    return ValidationOutcome(narrative=narrative, notes=notes, degraded=degraded)