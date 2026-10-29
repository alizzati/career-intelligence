# Dataset and Annotation Specification

Status: Step 17 design, no experimental execution.

## 1. Data categories

The evaluation framework recognizes three dataset classes that are distinct in status and scientific use:

- R (real CVs): CVs written by actual candidates; used for primary evaluation if collected under the protocol.
- S-H (synthetic human-authored): handcrafted profiles that emulate entry-level IT graduate CVs; used for robustness and failure-case tests.
- S-M (synthetic machine-generated): generated text from a model without human verification; not scientific evidence and must be labelled separately.

The repository does not contain a validated full evaluation corpus yet. Until one is constructed, the protocol is a design and annotation standard rather than a completed dataset.

## 2. Required dataset fields

Each evaluation record must contain enough information to reproduce the profile and compare outputs without relying on hidden context.

Required fields:

- `profile_id`
- `dataset_type` (R, S-H, S-M)
- `source_split` (train/dev/test or pilot/formal)
- `cv_text_redacted` or equivalent stored text input after redaction
- `normalized_user_skills` with canonical skill IDs when available
- `evidence_by_skill` with evidence type and description
- `career_target_reference` only when a target career is explicitly provided by the annotation process
- `annotation_version`
- `profile_hash` and `redaction_hash` for reproducibility

The system's actual Profile Agent persists only a whitelisted subset of fields and redacts PII before LLM exposure. This must be reflected in all dataset documentation.

## 3. Annotation principles

The annotation policy must preserve the project's architecture constraints and the research problem.

1. Annotators label only what appears in the CV text itself. They do not infer missing technologies or roles.
2. Skill extraction and canonicalization are done with the OKB catalog, without using the system's recommendation outputs as the source of labels.
3. A user claim without linked evidence remains a claim, not a confirmed skill.
4. Unmatched user claims are not treated as missing career requirements.
5. Annotation is blind to the candidate career recommendations and to the occupational skills of the target career when possible, so the labels are not contaminated by the KB mapping under evaluation.

## 4. Annotation schema

### 4.1 Career recommendation labels

For each profile and each canonical career:

- `relevant` / `not_relevant` for the profile-level ranking task, or a graded label if the study uses a preference scale.
- optional `evidence_excerpt` from the CV that supports the judgment.
- if a ground-truth target career is defined, record it as a separate field and do not overwrite the rank-based labels.

### 4.2 Skill extraction labels

For each extracted skill mention:

- `surface_term`
- `normalized_skill_id` if the skill maps to an existing KB skill
- `normalization_status`: matched / unmatched / ambiguous
- `evidence_type`: education / project / work / internship / certification / self-report / other
- `evidence_support`: linked / claimed-only / none

### 4.3 Skill-gap labels

For each required skill in a career's KB set, annotate the status as one of the canonical categories:

- `matched_evidenced`
- `matched_claimed_only`
- `missing`
- `unmatched_user_claims` (user claim with no KB mapping)

These categories must match the deterministic categories already used by `skill_gap_service.py` and the downstream schema, and they must not be reinterpreted as priority tiers.

## 5. Evidence grading

Evidence is graded by provenance strength, not by the LLM's opinion. The protocol should distinguish:

- supported evidence: direct project/work/education/certification evidence tied to the claim
- claimed-only evidence: self-reported or unlinked skill mention without a supporting artifact in the CV
- unsupported claim: claim not anchored in the CV text or not in the allowed evidence set

This distinction is especially important because the system design explicitly forbids treating a self-reported claim as equivalent to a verified skill.

## 6. Annotation workflow

The annotation workflow should follow this order:

1. Redact PII in the source CV text.
2. Provide annotators with the redacted profile, the 10-career label space, and the known skill catalog.
3. Ask annotators to extract explicit skill mentions and evidence.
4. Ask them to decide the relevance of each career using the CV text only.
5. Ask them to mark whether a skill claim is matched to a canonical skill, unmatched, or ambiguous.
6. Ask them to identify whether the evidence is linked or only self-reported.
7. Freeze the annotation version before any model-based evaluation runs.

Annotators must not be shown the system's computed scores or outputs when making labels for the primary scientific evaluation.

## 7. Quality control

- Use dual annotation on a development subset, then resolve disagreements with adjudication.
- Record inter-annotator agreement for skill extraction and career relevance labels.
- Keep a failure log for ambiguous or illegible CV text.
- Exclude facts that are not explicitly stated in the CV text.
- Do not treat external knowledge or occupation-labeled examples as source evidence unless explicitly provided by the CV itself.

## 8. KB dependency and validity gate

This protocol treats the OKB as a necessary but not sufficient source. The skill-gap and recommendation evaluation can only be interpreted as meaningful once the knowledge-base validity check is performed.

The evaluation must report:

- whether the KB evidence is accepted for the evaluation set,
- whether the career-skill mappings were audited,
- whether there are known gaps in coverage,
- whether any skill names present in user profiles are intentionally unmatched because they are not in the canonical skill catalog.

This is particularly important because the system may otherwise overstate skill-gap accuracy by measuring against its own KB assumptions.

## 9. Implementation constraints for Step 18

The dataset and annotation setup for Step 18 must include:

- an immutable dataset manifest with profile hashes and annotation version,
- a fixed evaluation split for dev/test,
- a redaction and text-extraction log,
- explicit handling of S-H vs S-M data,
- strict separation between annotation and model development data.

No experiment may treat any dataset as validated until the annotation process is complete and the version is frozen.
