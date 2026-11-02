# Design and Decision Freeze (T1)

**Status: COMPLETE — T1 design decisions frozen.** This document records the
approved baseline and researcher-approved conceptual contracts. T1 completion
freezes design decisions; it does not assert implementation readiness or that
any design item has been implemented. Implementation status remains
**UNKNOWN** unless a cited project record explicitly reports otherwise. No
source code, database, prompt, or application configuration was changed.

## Status labels

- **CONFIRMED** — explicitly fixed by `AGENTS.md`, the current T1 instruction,
  or a decision document with a clear approval status.
- **APPROVED** — explicitly approved by the researcher for this design freeze.
- **PROPOSED** — a design recommendation that has not been approved.
- **UNRESOLVED** — a material decision or contract is not sufficiently specified.
- **IMPLEMENTATION STATUS UNKNOWN** — a design decision exists, but this T1
  document has not audited the implementation against it.

## System Scope and Objectives

- **CONFIRMED** The system is a research prototype for IT graduates in
  Indonesia. It supports career recommendations, skill-gap analysis,
  personalized learning roadmaps, and verification of consistency and
  knowledge grounding. It supports exactly the 10 canonical careers in the
  existing OKB; it must not add career categories. Sources and claims must be
  limited to records actually available in the OKB and user evidence.
  (`AGENTS.md` §§1, 6.1; `docs/MASTER_SPEC.md` §§1–2.)
- **CONFIRMED** The evaluation objective is traceable, verifiable career
  guidance, interpreted within the research problem and objective recorded in
  `docs/evaluation/EVALUATION_PROTOCOL.md` §1. Official thesis research-question
  wording has not been found in the repository.
- **IMPLEMENTATION STATUS UNKNOWN** `docs/PROJECT_STATE.md` reports completion
  of prior pipeline stages, but this design-freeze task is not an
  implementation audit and does not verify each component or its current data.

## System Architecture

- **CONFIRMED** The intended dependency flow is OKB and deterministic retrieval;
  user competency profile; Profile Agent; Career Recommendation Agent;
  deterministic Skill-Gap Engine and explanatory Skill-Gap Agent; Learning
  Roadmap Agent; Verification Agent; orchestration; API; frontend; evaluation.
  This sequence does not authorize skipping incomplete dependencies.
  (`AGENTS.md` §3.)
- **CONFIRMED** Deterministic components own structured decisions and
  calculations. LLM-generated text may explain results but may not invent
  unsupported facts or change deterministic outputs. Reuse canonical IDs and
  existing interfaces. (`AGENTS.md` §§4, 6.2.)
- **CONFIRMED** Verification reports findings and must not silently mutate
  agent outputs. Any revision loop must have a configurable cap, revise only
  the responsible component, and verify again. Orchestration must not be
  implemented until the Verification Agent and its tests are complete.
  (`AGENTS.md` §6.2.)
- **CONFIRMED** Technology recognition, competency claims, and
  activity-derived competency candidates are separate conceptual processing
  paths; a technology mention alone is not competency evidence. (Current T1
  instruction, sections B–D.)
- **APPROVED** After profile extraction, retain technology claims separately;
  normalize competency claims to canonical skills; extract Activities from
  Experience/Projects; then create and verify Activity–Skill candidates before
  adding accepted evidence to the profile used by career fit. The original
  extracted claim/activity records remain immutable. Approval is required
  before implementation.
- **IMPLEMENTATION STATUS UNKNOWN** The architecture is documented as
  implemented through earlier stages in `docs/PROJECT_STATE.md`; Technology
  Normalization and activity-candidate processing are listed as outstanding in
  `docs/master_checklist_pra_ablation.md`. This T1 document does not resolve
  that implementation gap.

## Occupational Knowledge Base

- **CONFIRMED** The OKB is the authoritative source for canonical careers,
  canonical skills, career-skill relationships, supported occupational
  information, and available provenance. Retrieval is deterministic. Do not
  invent records, requirements, provenance, or learning resources.
  (`AGENTS.md` §§4, 6.1–6.2.)
- **CONFIRMED** The project specification describes relational entities
  including careers, occupations, career-occupation links, skills,
  career-skill links, SKKNI standards, competency units, tasks, technologies,
  provenance, and source evidence. (`docs/MASTER_SPEC.md` §§2–3.)
- **CONFIRMED** Technology-to-competency mapping is optional and requires
  source/provenance. A technology signal must not itself affect career-fit or
  skill-gap results. (Current T1 instruction, section B.)
- **IMPLEMENTATION STATUS UNKNOWN** `docs/PROJECT_STATE.md` reports a verified
  10-career/87-skill/155-career-skill isolated-database snapshot for the
  October 2026 diagnostic. The T1 instruction specifically prohibits assuming
  that the inspected workbook is imported into PostgreSQL or that its
  technology catalog matches the run-time database.
- **CONFIRMED** Evaluation and diagnostic runs must identify the OKB snapshot
  or content fingerprint; version information must not be invented.
  (`docs/evaluation/REPRODUCIBILITY_SPEC.md` §§3, 5.)
- **APPROVED** Identify a snapshot using a stable ID plus SHA-256 manifest of
  canonicalized, deterministically ordered table exports, with source-file
  hash/import metadata recorded separately. Read-only verification must
  establish workbook/database parity. This format does not assert parity or
  authorize an import; producing the actual import/parity report remains a T4
  deliverable.
- **IMPLEMENTATION STATUS UNKNOWN** The isolated database snapshot described
  in `PROJECT_STATE.md` is historical diagnostic evidence, not proof of the
  present database contents or workbook import state. T4 still requires a
  source, import, and integrity report.

## Data and Entity Contracts

- **CONFIRMED** User/profile data is distinct from occupational data. A
  competency claim without accepted evidence is not automatically missing;
  canonical IDs and evidence references must be retained where available.
  (`docs/MASTER_SPEC.md` §4; `AGENTS.md` §§4–5.)
- **CONFIRMED** Preserve the project's existing four skill-gap categories
  exactly: `matched_evidenced`, `matched_claimed_only`, `missing`, and
  `unmatched_user_claims`. An unmatched user claim is not a missing career
  requirement. (`AGENTS.md` §§5, 6.1.)
- **CONFIRMED** Technology claims and competency claims are distinct. A
  technology-to-competency mapping must be provenance-backed and cannot
  silently confer competency claim/evidence status. (Current T1 instruction,
  sections B and D.)
- **CONFIRMED** Activity-derived candidates must use canonical skills from the
  OKB; each Activity → Skill relation is independently verified. Only a
  passing relation may become competency evidence. Avoid duplicate credit for
  the same activity or evidence. (Current T1 instruction, section C.)
- **APPROVED — conceptual contract:** Keep distinct records with
  stable IDs and `profile_id`: (a) `TechnologyClaim` stores sanitized surface
  term, source reference, nullable canonical `technology_id`, and
  `matched`/`unmatched` status; (b) `CompetencyClaim` stores sanitized surface
  term, source reference, nullable canonical `skill_id`, and
  `matched`/`unmatched` status; (c) `Activity` stores type
  (`experience` or `project`), sanitized source text/reference, and source
  section; (d) `ActivitySkillCandidate` stores `activity_id`, canonical
  `skill_id`, source reference, and independent verification findings; and (e)
  `CompetencyEvidence` stores canonical `skill_id`, evidence origin/reference,
  and accepted status. Preserve canonical references and source traceability;
  unknown IDs remain unmatched, never fabricated. Original extracted records
  are immutable.
- **APPROVED — lifecycle:** preserve extracted source
  records; normalize explicit competency claims; extract activities; generate
  only OKB-canonical skill candidates; independently verify each relationship;
  create Competency Evidence only for PASS candidates; keep REVISE candidates
  pending explicit owner revision and re-verification; retain FAIL findings
  without evidence credit. An explicitly claimed competency without accepted
  supporting evidence remains `matched_claimed_only`; unmatched claims remain
  `unmatched_user_claims`.
- **APPROVED — evidence acceptance:** only a PASS Activity–Skill relationship
  may create activity-derived CompetencyEvidence. Technology mentions alone
  never create competency claims or evidence. Do not automatically accept
  self-reported skills, certificates, education records, or other non-activity
  records as `matched_evidenced`; do not introduce a non-activity
  evidence-processing pipeline in this scope. Such evidence remains
  unaccepted unless an explicitly approved verification mechanism exists.
- **APPROVED — deduplication:** enforce at most one accepted
  Activity–Skill evidence credit for the same stable `activity_id` and
  canonical `skill_id`. A repeated extraction of the same source activity
  should resolve to the same activity identity; a distinct activity may
  independently evidence the same skill. Do not merge distinct activities
  solely because their wording is similar. Reuse of the same underlying source
  excerpt across different activity records must not create additional credit.
- **T3 detail:** storage/API schema, source-span representation, and retention
  mechanics may be specified during data-model alignment, consistently with
  these approved conceptual contracts. They do not block T1 closure.
- **IMPLEMENTATION STATUS UNKNOWN** Existing project schemas document user
  skills/evidence but do not establish these approved conceptual claim/activity
  records.
- **IMPLEMENTATION STATUS UNKNOWN** `docs/MASTER_SPEC.md` §3 lists logical
  entities, but it does not define the approved claim/activity contracts above.
  `docs/PROJECT_STATE.md` describes existing user and occupational records;
  it does not establish that the proposed contracts exist.

## Claim and Activity Processing

- **CONFIRMED** Technology Normalization uses a global technology catalog and
  aliases. Technology recognition does not itself produce a canonical
  competency claim, evidence, career-fit contribution, or skill-gap result.
  Any explicit technology-to-competency link is optional and provenance-backed.
  (Current T1 instruction, section B.)
- **CONFIRMED** Explicit competency claims without accepted evidence may be
  classified `matched_claimed_only`; claims not matchable to canonical skills
  remain `unmatched_user_claims`. Technologies must not be converted into
  either category automatically. (Current T1 instruction, section D;
  `AGENTS.md` §6.1.)
- **CONFIRMED** Experience and Projects may produce candidate canonical
  competencies. The Activity → Skill inference must be independently assessed
  for source traceability, semantic relevance, inference validity, and evidence
  sufficiency. Only PASS may create accepted competency evidence. REVISE
  requires an explicit revision step; no silent verifier edits. (Current T1
  instruction, sections C–D.)
- **APPROVED — technology aliases:** use the global OKB
  technology catalog with an explicit alias list per canonical technology.
  Apply Unicode NFKC, case-folding, and whitespace normalization before exact
  matching against canonical names or registered aliases. Do not use fuzzy
  matching to assign canonical technology IDs. Alias collisions across
  technology IDs are catalog validation errors. Record catalog
  snapshot/fingerprint and source provenance for aliases and optional
  technology-to-competency references. These contextual references never
  create competency evidence or directly affect career-fit/skill-gap.
- **APPROVED — activity candidate source:** candidate
  generation may use only sanitized Experience/Project source text and existing
  canonical OKB skill IDs. Every candidate keeps a pointer to the originating
  Activity; tool-name mentions alone are insufficient evidence of a broader
  competency.
- **APPROVED — evidence boundary:** self-reported skills and non-activity
  evidence (including certificates and education records) are not
  automatically accepted as `matched_evidenced`. Only PASS Activity–Skill
  relationships create activity-derived evidence in this scope. No
  non-activity evidence-processing pipeline is authorized unless an explicit
  verification mechanism is separately approved. The archived evaluation
  draft flags that current code may treat any evidence row, including
  self-report, as linked; this remains an implementation-audit risk, not an
  unresolved T1 decision. (`docs/evaluation/evaluation.md` §7, RISK-07.)
- **IMPLEMENTATION STATUS UNKNOWN** `docs/master_checklist_pra_ablation.md`
  lists technology, competency, activity, and candidate-processing pipelines
  as future implementation work. The exact current behavior is not established
  by T1.

## Agent Responsibilities

| Component | Frozen responsibility and boundary | Implementation status |
|---|---|---|
| Deterministic retrieval / OKB access | Retrieve canonical records and relationships; do not fabricate missing data. | **IMPLEMENTATION STATUS UNKNOWN** for T1; prior stages are reported complete in `PROJECT_STATE.md`. |
| Profile Agent | Extract structured profile facts and competency claims; normalize against canonical skills; do not recommend careers or upgrade bare claims to verified skills. | **CONFIRMED** boundary (`AGENTS.md` §§3–4; `MASTER_SPEC.md` §5). **IMPLEMENTATION STATUS UNKNOWN** for this freeze. |
| Technology Normalizer | Match technology mentions against global technology catalog and aliases; keep results separate from competency evidence and scoring. | **CONFIRMED** boundary and **APPROVED** alias contract; implementation not audited. |
| Activity candidate processing | Produce only canonical-skill candidates from Experience/Projects and preserve the source Activity → Skill trace. | **CONFIRMED** boundary and **APPROVED** conceptual contract; implementation not audited. |
| Career Recommendation Agent | Use all supported canonical careers and the single deterministic career-fit result; LLM may explain, not rescore or invent requirements. | **CONFIRMED** (`AGENTS.md` §§4, 6.1). Implementation not audited here. |
| Skill-Gap Engine | Own the authoritative classification using the existing four categories and shared career-fit service. | **CONFIRMED** (`AGENTS.md` §§4–5, 6.1). Implementation not audited here. |
| Skill-Gap Agent | Explain the deterministic gap result; do not independently recalculate or modify it. | **CONFIRMED** (`AGENTS.md` §6.1). Implementation not audited here. |
| Learning Roadmap Agent | Generate roadmap from existing skill-gap results; do not recalculate career fit/gaps or invent unsupported requirements/resources. | **CONFIRMED** (`AGENTS.md` §§4, 6.1). Implementation not audited here. |
| Verification Agent | Evaluate structured consistency, canonical IDs, provenance, activity-candidate relations, evidence sufficiency, and generated text; report PASS/REVISE/FAIL without silently rewriting outputs. | **CONFIRMED** (`AGENTS.md` §6.2; researcher T1 approval, sections C and E). Activity rubric **APPROVED** above. |
| Orchestrator | Pass source outputs unchanged, cap revisions, route only to responsible component, re-verify. | **CONFIRMED** (`AGENTS.md` §6.2). Implementation and activity-pipeline integration not audited here. |

## Verification Rules

- **CONFIRMED** Validate canonical IDs and career-skill relationships,
  deterministic score consistency, schemas, roadmap coverage, and provenance
  only against source records actually present in the OKB.
  (`AGENTS.md` §6.2.)
- **CONFIRMED** Distinguish `PASS`, `FAIL`, and `REVISE`. Findings must be
  explicit; the verifier must not silently replace source outputs. A revision
  loop must be capped, responsible-component-only, and followed by verification.
  (`AGENTS.md` §6.2.)
- **CONFIRMED** Each Activity → Skill candidate requires independent checks for
  source traceability, semantic relevance, inference validity, and evidence
  sufficiency. Only PASS may yield Competency Evidence. Outcomes are PASS,
  REVISE, or FAIL; REVISE is not a pass and requires explicit revision and
  re-verification. (Current T1 instruction, sections C and E.)
- **APPROVED — rubric:** evaluate each dimension separately
  with status and a concise reason/source reference. (1) Traceability PASS only
  when the cited Activity resolves to the sanitized source record; FAIL when
  absent or contradictory. (2) Semantic relevance PASS only when the described
  action/output supports the canonical skill meaning; FAIL when unrelated.
  (3) Inference validity PASS only when the skill follows from the described
  action/output without relying on title, tool mention, or general assumptions;
  FAIL for a leap unsupported by the text. (4) Evidence sufficiency PASS only
  when the source describes an attributable concrete action or output, not a
  bare assertion/tool list; otherwise REVISE if clarification could resolve it,
  FAIL if evidence is absent or irrecoverably insufficient. Overall PASS
  requires all four PASS; otherwise FAIL takes precedence over REVISE, and
  REVISE applies only when no dimension is FAIL and at least one is REVISE.
  No numeric threshold is proposed.
- **APPROVED — explicit revision:** a responsible candidate
  producer may revise only fields identified by verifier feedback, preserving
  the original candidate and finding; rerun all four checks. Apply the existing
  configured workflow revision cap; exhausted or unowned REVISE ends
  non-passing and grants no evidence credit. The Verification Agent must never
  silently rewrite evidence. No new numeric threshold is introduced.
- **IMPLEMENTATION STATUS UNKNOWN** Project documentation reports a verifier
  for existing pipeline outputs. Activity-candidate verification is not
  established by those reports.

## Career Fit and Skill-Gap Rules

- **CONFIRMED** `app/services/career_fit_service.py::compute_career_fit()` is
  the sole source of career-fit calculations. Do not change its formula or
  scoring rules as part of this design freeze. (`AGENTS.md` §§4, 6.1; current
  T1 instruction, section A.)
- **CONFIRMED** Step 9's deterministic skill-gap result is authoritative.
  Preserve exactly `matched_evidenced`, `matched_claimed_only`, `missing`, and
  `unmatched_user_claims`; do not add categories, priority tiers/scores, or
  proficiency-gap calculations. Unmatched claims are not missing requirements.
  (`AGENTS.md` §§5, 6.1.)
- **CONFIRMED** Evidence-free competency claims can be `matched_claimed_only`;
  accepted activity-derived competency evidence can support
  `matched_evidenced` even without an explicit Skills-section claim. Technology
  mentions alone support neither. (Current T1 instruction, section D.)
- **CONFIRMED** Technology recognition or technology-to-competency candidates
  must not directly change fit or gap calculations. Any competency effect must
  be mediated by a valid canonical competency claim/evidence relationship.
  (Current T1 instruction, sections B and D.)
- **CONTRADICTION — resolved by approved frozen decision:** `docs/MASTER_SPEC.md`
  §6 proposes `partial`, `uncertain`, and prioritized gaps with required/user
  proficiency levels; §§7 and 12 also propose priority, proficiency,
  dependencies, semantic similarity, and configurable weighted factors.
  `AGENTS.md` §§5 and 6.1 explicitly supersede those older choices: retain the
  four established categories, do not add priorities or proficiency-gap
  calculations, and keep the existing career-fit implementation as sole source.
  The legacy text is retained as historical requirements, not the current
  design contract.
- **IMPLEMENTATION STATUS UNKNOWN** The shared calculation is identified as
  the existing source of truth in project instructions. Its implementation and
  tests are for the later implementation audit, not this T1 document.

## Learning Roadmap Rules

- **CONFIRMED** The roadmap consumes the existing skill-gap result and must not
  recalculate career fit or gaps. Its items must remain grounded in the selected
  career and available OKB context; no invented resources, prerequisites,
  proficiency levels, timelines, or occupational requirements.
  (`AGENTS.md` §§4, 6.1.)
- **CONFIRMED** Verification evaluates roadmap identity, evidence, and coverage
  but does not silently rewrite the roadmap. (`AGENTS.md` §6.2.)
- **CONTRADICTION — resolved by approved frozen decision:** `docs/MASTER_SPEC.md`
  §7 proposes dependency-based sequences, priorities, proficiency-driven
  stages, and learning resources. Those are not current commitments because
  `AGENTS.md` §§4 and 6.1 prohibit inventing unsupported learning resources,
  prerequisites, proficiency levels, and skill-gap priorities.
- **UNRESOLVED** The accepted learning-resource source/contract and any
  dependency or pedagogical sequencing policy are not specified; until approved
  and supported by OKB records, they must not be generated as facts.
- **IMPLEMENTATION STATUS UNKNOWN** The roadmap is reported as an existing
  component in `docs/PROJECT_STATE.md`; T1 does not audit behavior.

## Experiment Configurations

The four configurations and named comparisons below are **CONFIRMED** by the
current T1 instruction, `AGENTS.md` frozen decisions, and
`docs/evaluation/EVALUATION_PROTOCOL.md` §4. Do not add, remove, or alter them.

| Configuration | Required behavior |
|---|---|
| **B0** | LLM-only. No OKB relationships, deterministic career-fit/skill-gap calculation, or Verification Agent. It may receive the fixed 10-career label space. |
| **B2** | LLM receives all 10 careers and their complete Career–Skill relationship sets from the OKB; the LLM performs matching and scoring. No deterministic `compute_career_fit()` or skill-gap calculation; no Verification Agent. |
| **B3** | OKB plus deterministic matching/scoring and skill-gap classification; no Verification Agent or revision loop. Keep unrelated validation and deterministic rules. |
| **F** | B3 plus Verification Agent and a bounded revision loop. Findings are reported; revise only the responsible component and re-verify. |

Primary comparisons:

- **F vs B0** — overall proposed system versus LLM-only baseline; not a
  component-level causal attribution.
- **F vs B3** — contribution of verification/revision, with other inputs and
  settings controlled.
- **B2 vs B3** — LLM-driven versus deterministic matching/scoring with the
  same occupational relationship information.

- **CONTRADICTION — legacy definitions superseded:** `docs/MASTER_SPEC.md`
  §§20–21 describes generic feature toggles and a different A/B/C/D matrix,
  including a KB-off + Verification-on arm. This conflicts with the frozen
  B0/B2/B3/F definitions and is superseded by `AGENTS.md` §6.1 and the current
  T1 instruction. The legacy matrix must not be used to configure experiments.
- **CONFIRMED — legacy wording superseded for experiment setup:**
  `docs/evaluation/DECISIONS.md` OP-04 recommends “relevant” KB relationship
  data and `EXPERIMENT_SPEC.md` §2 uses similar wording, while this T1
  instruction requires all 10 career-skill relationship sets. The all-10 scope
  is the controlling decision. The evaluation documents now reflect that
  scope, with the old OP-04 wording preserved in the decision change record.
  This documentation conflict no longer leaves B2's experiment scope
  undecided.
- **IMPLEMENTATION STATUS UNKNOWN** `docs/evaluation/DECISIONS.md` and
  `METRICS_IMPLEMENTATION.md` describe configuration definitions as descriptive
  only and say runtime switching/runner are not implemented. T1 does not
  validate code paths.

## Evaluation Requirements

- **CONFIRMED** The intended comparisons are F vs B0, F vs B3, and B2 vs B3.
  Keep the same evaluation data across configurations; control profile, OKB
  snapshot, model/provider settings, and relevant prompts where a comparison
  requires parity. (`docs/evaluation/EVALUATION_PROTOCOL.md` §§4–5.)
- **CONFIRMED** Evaluation requires independent reference labels; the system
  output or OKB alone must not be presented as independent ground truth.
  Annotate redacted CV content, preserve the claim/evidence distinction, use
  blind annotation where practical, adjudicate disagreements, and report
  coverage and limits. (`docs/evaluation/DATASET_AND_ANNOTATION.md` §§1–8.)
- **CONFIRMED** Documented metrics include career ranking (Hit@k, nDCG@k),
  skill-gap classification, verification behavior under controlled fault
  injection, traceability, roadmap coverage/grounding, stability, and
  operational measures. Unmatched user claims are evaluated separately as a
  claim set, not as missing required skills. (`docs/evaluation/EVALUATION_PROTOCOL.md`
  §6; `METRICS_IMPLEMENTATION.md` §§3–5.)
- **CONFIRMED** Knowledge-base validity must be assessed before interpreting
  downstream recommendation or gap correctness. Label-dependent measurements
  remain unavailable without validated annotations. (`EVALUATION_PROTOCOL.md`
  §6; `DECISIONS.md` completion checklist.)
- **UNRESOLVED — formal evaluation prerequisite, not a T1 contract blocker:**
  Official thesis proposal research questions are not available in the
  repository; evaluation questions are explicitly derived, not official.
  (`DECISIONS.md` OP-01; `EVALUATION_PROTOCOL.md` §1.) Do not label derived
  questions as official; confirm wording against the approved thesis proposal
  before formal evaluation claims.
- **UNRESOLVED** The validated real-CV dataset, expert ground truth, annotation
  agreement/adjudication outputs, and final evaluation split are not available
  as completed artifacts. Formal experiments must wait for the applicable
  quality gates.
- **UNRESOLVED** E8 weight sensitivity and E9 knowledge-base validity are
  specified in `EXPERIMENT_SPEC.md` but reported as not implemented in
  `METRICS_IMPLEMENTATION.md` §8.
- **IMPLEMENTATION STATUS UNKNOWN** `docs/PROJECT_STATE.md` reports the Step 17
  metric layer implemented and tested but Step 18–20 execution outstanding.
  The experiment runner and runtime switching are explicitly not established
  by the evaluation docs. No formal run is claimed here.

## Unresolved Decisions and Risks

All six proposals from the previous draft are approved by the researcher,
subject to the explicit evidence-acceptance clarification below. The decision
log records these as newly approved decisions. Remaining details and risks
belong to later stages:

- **APPROVED — data and lifecycle contracts:** five conceptual entities,
  immutable extracted records, stable IDs, profile ownership, canonical
  references, and source traceability.
- **APPROVED — evidence acceptance:** explicitly claimed competencies without
  accepted support remain `matched_claimed_only`; only PASS Activity–Skill
  relations create activity-derived evidence. Technology mentions do not
  create competency claims/evidence. Self-report and non-activity records are
  not automatically accepted, and no non-activity evidence pipeline is in
  scope absent separate approval.
- **APPROVED — verification and revision:** four independent checks and the
  specified PASS/FAIL/REVISE aggregation; explicit responsible-component
  revision and re-verification under the existing cap; no silent evidence
  rewrite or new numeric threshold.
- **APPROVED — duplicate credit:** at most one accepted credit per stable
  Activity ID/canonical Skill ID pair; distinct activities may independently
  support the same skill.
- **APPROVED — technology aliases:** global catalog, explicit aliases,
  NFKC/case-fold/whitespace normalization, exact matching, and validation
  errors on cross-ID alias collisions; no fuzzy canonical assignment.
- **APPROVED — OKB reproducibility snapshot:** stable ID, SHA-256 fingerprint
  of canonicalized deterministically ordered table exports, original source
  hash, and import metadata. This does not claim that workbook/database
  parity exists.
- **APPROVED — B2 scope:** all 10 careers and complete Career–Skill
  relationship sets are supplied to the LLM. The conflicting legacy wording
  has been reconciled in the evaluation decision and experiment documents;
  its prior wording remains recorded as superseded history.

Later-stage prerequisites and risks:

- **T3 detail:** finalize concrete storage/API and source-span representation
  consistently with the approved conceptual contracts.
- **T4 prerequisite:** produce the actual OKB import, parity, and integrity
  reports; do not assume workbook/database parity.
- **UNRESOLVED — formal evaluation prerequisite:** obtain the approved thesis
  proposal's official research questions before representing derived
  evaluation questions as official.
- **T10 prerequisite:** pin or document model, provider, inference settings
  and manifest treatment, including unavailable seed/temperature controls.
- **T9 prerequisite:** complete dataset annotation, quality control, KB
  validity review, and final split before experiments.

### Decision log

| Decision | Status | Record |
|---|---|---|
| Exactly 10 canonical careers; `compute_career_fit()` is the sole career-fit calculator. | **APPROVED — prior decision** | `AGENTS.md` §§4, 6.1 |
| Step 9 is authoritative for skill-gap results; preserve exactly four categories and do not add priority/proficiency-gap rules. | **APPROVED — prior decision** | `AGENTS.md` §§5, 6.1 |
| Technology mentions cannot themselves establish competency evidence or alter fit/gap; technology links require provenance. | **APPROVED — prior decision** | `AGENTS.md` §§4, 6.1; researcher T1 instruction |
| Only PASS Activity–Skill candidates create activity-derived evidence; preserve explicit findings and bounded revision/re-verification. | **APPROVED — prior decision, clarified here** | `AGENTS.md` §6.2; researcher T1 instruction |
| B0/B2/B3/F and comparisons F-vs-B0, F-vs-B3, B2-vs-B3 remain fixed; B2 supplies all 10 full relationship sets. | **APPROVED — prior and researcher-approved** | `AGENTS.md` §6.1; researcher T1 instruction |
| Five conceptual entity contracts, immutable records, lifecycle and canonical/source references. | **APPROVED — researcher decision** | Researcher approval, 2026-11-02 |
| Evidence-acceptance boundary, including self-report and non-activity evidence. | **APPROVED — researcher decision** | Researcher approval, 2026-11-02 |
| Four-check rubric, status aggregation, explicit revision and existing cap. | **APPROVED — researcher decision** | Researcher approval, 2026-11-02 |
| Duplicate-credit identity and policy. | **APPROVED — researcher decision** | Researcher approval, 2026-11-02 |
| Technology catalog alias normalization, exact match and collision policy. | **APPROVED — researcher decision** | Researcher approval, 2026-11-02 |
| OKB snapshot ID/fingerprint/source hash/import metadata format. | **APPROVED — researcher decision** | Researcher approval, 2026-11-02 |
| Official research-question wording and completed evaluation artifacts. | **LATER-STAGE PREREQUISITE** | T4/T9/T10; evaluation readiness documents |

### Contradiction register

| Topic | Version A | Version B / resolution | Status |
|---|---|---|---|
| Skill-gap classes and ranking | `MASTER_SPEC.md` §§6–7 proposes partial/uncertain gaps, priorities, proficiency levels and sequencing. | `AGENTS.md` §§5, 6.1 fixes four categories and prohibits priority/proficiency-gap rules. | **CONFIRMED** frozen rule supersedes legacy proposal; document the historical conflict. |
| Career-fit formula | `MASTER_SPEC.md` §12 proposes configurable weighted factors including optional semantic similarity. | `AGENTS.md` §§4, 6.1 makes `compute_career_fit()` the only source and bars competing calculations. | **CONFIRMED** frozen rule supersedes the older conceptual proposal. |
| Ablation matrix | `MASTER_SPEC.md` §§20–21 proposes generic toggles and A/B/C/D, including KB-off + verification-on. | Current T1 instruction and `AGENTS.md` §6.1 require exactly B0/B2/B3/F and named comparisons. | **CONFIRMED** use B0/B2/B3/F; no extra arm. |
| B2 information scope | `DECISIONS.md` OP-04 and `EXPERIMENT_SPEC.md` §2 previously used “relevant” relationship wording. | Researcher-approved requirement: all 10 careers and their complete Career–Skill relationship sets. | **RECONCILED:** evaluation docs updated; prior wording retained as superseded history. |
| Roadmap scope | `MASTER_SPEC.md` §7 proposes priorities, proficiency, dependencies and staged resources. | `AGENTS.md` §§4, 6.1 bars unsupported resources, prerequisites, proficiency levels and priorities. | **CONFIRMED** frozen rule controls; unsupported enrichment is not authorized. |

### T1 exit criteria and decision

| T1 exit criterion | Result | Evidence |
|---|---|---|
| Approved baseline and frozen constraints recorded | **PASS** | Architecture, `compute_career_fit()` sole-source rule, four skill-gap categories, and fixed experiment arms/comparisons are documented above. |
| Conceptual entities, lifecycle, evidence acceptance, and duplicate-credit policy resolved | **PASS** | Researcher-approved decisions and explicit non-activity evidence boundary recorded under “Data and Entity Contracts.” |
| Activity verification rubric and revision behavior resolved | **PASS** | Four independent checks, PASS/FAIL/REVISE aggregation, explicit responsible-component revision, and existing cap recorded under “Verification Rules.” |
| Technology catalog and alias handling resolved | **PASS** | Global catalog, explicit aliases, exact normalized matching, collision errors, provenance, and non-scoring boundary recorded under “Claim and Activity Processing.” |
| OKB reproducibility identification format resolved | **PASS** | Snapshot ID, canonical table-export SHA-256, source-file hash, and import metadata recorded under “Occupational Knowledge Base”; actual parity remains T4. |
| Experiment definitions and B2 occupational-information scope reconciled | **PASS** | All-10 scope is recorded here and in both evaluation documents; previous wording is retained as superseded history. |
| T1 design-freeze deliverable and stage hand-off recorded | **PASS** | This document and `docs/master_checklist_pra_ablation.md` mark T1 complete and T2 next. |

**T1 status: COMPLETE.** All design decisions in T1's scope are resolved.
Official thesis research-question wording and dataset/ground-truth preparation
remain later evaluation prerequisites, not unresolved T1 system-contract
decisions. T1 completion does not establish implementation readiness. T2 —
Implementation Audit is the next active stage and has not started.

## Source documents reviewed

- `AGENTS.md`
- `instruction.md` (current T1 task)
- `docs/MASTER_SPEC.md`
- `docs/PROJECT_STATE.md`
- `docs/master_checklist_pra_ablation.md`
- `docs/evaluation/DECISIONS.md`
- `docs/evaluation/EVALUATION_PROTOCOL.md`
- `docs/evaluation/EXPERIMENT_SPEC.md`
- `docs/evaluation/DATASET_AND_ANNOTATION.md`
- `docs/evaluation/REPRODUCIBILITY_SPEC.md`
- `docs/evaluation/METRICS_IMPLEMENTATION.md`
- `docs/evaluation/evaluation.md`
- `docs/DIAGNOSTIC_CV_TESTING.md`
- `docs/manual_validation.md`
