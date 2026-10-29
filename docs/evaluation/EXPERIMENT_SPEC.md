# Experimental Specification

Status: Step 17 design, not executed.

## 1. Experiment objective

The experiments are designed to compare the complete pipeline against the relevant baselines, while respecting the actual repository architecture. They are not a full benchmark suite and must not be treated as already run.

Three primary comparisons are defined in the protocol:

- C1: F vs B0
- C2: F vs B3
- C3: B2 vs B3

The Step 18 implementation is responsible for wiring these runs into the actual runner, not this document.

## 2. Required configuration behaviors

### B0 configuration

B0 must use the LLM-only logic and no OKB access.

Required behavior:

- user CV text or already-structured profile is supplied
- the LLM sees only the 10-career recommendation space and the profile text
- no `retrieval_service` call for `career_skills`, `get_all_careers`, or `get_occupational_context`
- no deterministic `compute_career_fit()` calculation
- no Verification Agent

### B2 configuration

B2 must include the KB occupational relationships while leaving matching/scoring to the LLM.

Required behavior:

- prompt includes relevant KB skill names and the canonical 10-career space
- needed relationship data is passed in a structured form, not hidden in a free-form explanation
- the LLM decides career ranking and gap status itself
- no `compute_career_fit()` call, no `skill_gap_service` call

### B3 configuration

B3 is the system path without verification.

Required behavior:

- use `retrieval_service` for the full context needed by the real system
- compute recommendation scores using `compute_career_fit()`
- compute skill-gap classification using `classify_skill_gap()`
- generate a roadmap as in the normal workflow
- omit only the Verification Agent and the revision loop; keep all non-verification checks, schema validation, and deterministic logic in place

### F configuration

F is the complete path.

Required behavior:

- all of B3, plus the `VerificationAgent`
- revision loop with `max_revisions`
- report failed checks, and rerun only the responsible stage when a verifier finding identifies a responsible owner
- do not mutate original outputs silently; verification is descriptive and reports findings only

## 3. Experiment list

| ID | Purpose | Configs | Output |
|---|---|---|---|
| E1 | extraction and normalization quality | B0, B2, B3, F | skill extraction, normalization, evidence attribution |
| E2 | recommendation quality | B0, B2, B3, F | Hit@k, nDCG@k |
| E3 | skill-gap classification quality | B0, B2, B3, F | status macro-F1 and per-category metrics |
| E4a | verification detection | F vs B3 | unsupported-claim recall and precision under fault injection |
| E4b | verification revision behavior | F vs B3 | resolution rate, repeated-run outcomes |
| E5a | output stability | B2, B3, F | variance across repeated runs |
| E5b | traceability | B3, F | traceability level distribution |
| E6 | roadmap coverage | B3, F | missing-skill coverage and grounding |
| E7 | operational metrics | all configs | latency, failure rate, token usage |
| E8 | weight sensitivity | B3, F | effect of all weight settings on ranking and status |
| E9 | knowledge-base validity audit | all configs | coverage and provenance quality of KB relationships |

### E1: extraction and normalization

This experiment measures whether the extracted user skills are correctly matched to the KB and how often they are unsupported or ambiguous.

Required outputs:

- precision/recall/F1 for normalized skill matches
- false-match rate for unsupported or ambiguous claims
- evidence attribution rate by evidence type

### E2: recommendation quality

This is the ranking experiment for the top careers.

Required outputs:

- Hit@1 and Hit@3
- nDCG@3
- tie-aware reporting where ties exist

### E3: skill-gap quality

This experiment measures the skill-gap classification quality, using the canonical four statuses defined by the repository.

Required outputs:

- macro-F1 for status classification
- category-wise precision/recall/F1
- over-credit and false-match rate when evidence is weak

### E4a / E4b: verification behavior

Fault-injected runs must be created under controlled conditions so the effect of the verifier can be evaluated without comparing different output states.

Required outputs:

- unsupported claim detection rate
- false-positive rate
- first-pass vs revision outcomes
- percentage of checks resolved without changing the underlying deterministic results

### E5a / E5b: stability and traceability

Stability is measured across repeated runs of the same input and configuration. Traceability is measured by whether each recommendation and each gap item can be tied back to a resolvable KB record or explicit user evidence.

### E6: roadmap coverage

Roadmaps must be evaluated as a grounded output of the deterministic skill-gap result, not as an independent re-interpretation of the user's profile. The metric is coverage and grounding, not pedagogical success claims.

### E7: operational metrics

This is a secondary but necessary experiment category for reproducibility and runtime quality.

Required outputs:

- total runtime per profile
- failure rate
- token usage
- API-call count
- number of retries or revision loops triggered

### E8: weight sensitivity

A configuration-level sensitivity run helps identify whether small weight changes materially alter rankings or gap classification. This is exploratory and does not change the deterministic source-of-truth formula.

### E9: KB validity audit

This is not an LLM benchmark. It audits the legitimacy of the requirement set being used in the skill-gap and recommendation evaluation.

Required outputs:

- number of skills with provenance
- number of sparse or missing evidence mappings
- proportion of skills with unresolved provenance
- explicit statement of whether the KB is valid enough to support the downstream claims

## 4. Execution rules for Step 18

The Step 18 implementation must ensure:

- each run stores a manifest with `user_id`, profile hash, config id, model id, prompt hash, KB fingerprint, and working-tree revision state
- the same profile is reused across F and B3 for valid comparison
- B0 and B2 do not accidentally receive the same hidden KB context via a shared prompt builder
- experiment output is written only to designated paths, never to production tables
- any model default values are recorded as defaults rather than silently assumed as pinned settings

## 5. No-execution rule for Step 17

This specification intentionally does not execute the formal runs. The design is complete enough to guide Step 18 implementation, but no pilot or formal experiments are conducted in this step.
