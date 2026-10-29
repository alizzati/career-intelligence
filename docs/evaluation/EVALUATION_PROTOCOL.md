# Evaluation Protocol (Step 17)

Status: Step 17 design document, read-only, no experiment execution.

## 1. Research source and scope

This evaluation protocol is anchored to the research context supplied in the Step 17 continuation brief:

- Research problem: "Bagaimana menghasilkan recommendation career yang traceable dan dapat diverifikasi prosesnya dalam membantu lulusan baru bidang IT memahami pilihan karier dan langkah pengembangan skill yang diperlukan."
- Research objective: "Untuk merancang, membangun, dan mengevaluasi hybrid verified multi-agent system yang dapat membantu lulusan baru bidang IT dalam menentukan karier yang sesuai, memahami kesenjangan keterampilan, serta memperoleh learning roadmap yang sesuai dengan occupational knowledge dan evidence kompetensi pengguna."
- Research constraints: exactly 10 canonical careers; hard-skill only; no external crawling; CV text only; fresh IT graduates/final-year students.

The protocol below operationalizes the objective without inventing official thesis research questions. Where formal RQs are needed, they are clearly labelled as derived evaluation questions, not as the thesis proposal's official wording.

## 2. Repository-grounded implementation facts

The following are taken from the actual repository implementation and are therefore the reference for all evaluation design:

- `backend/app/services/retrieval_service.py` is the single read-only KB access layer.
- `backend/app/services/career_fit_service.py::compute_career_fit()` is the authoritative deterministic calculator.
- `backend/app/services/skill_gap_service.py` is the deterministic skill-gap engine.
- `backend/app/agents/career_recommendation_agent.py` enumerates all careers, computes deterministic scores, and then asks for reasoning text only after scoring.
- `backend/app/agents/skill_gap_agent.py` explains a deterministic skill-gap result but does not recalculate it.
- `backend/app/agents/learning_roadmap_agent.py` consumes skill-gap results and does not recalculate career fit or skill gaps.
- `backend/app/agents/verification_agent.py` checks canonical IDs, deterministic score consistency, skill-gap categories, roadmap coverage, and grounding against returning KB context. It reports findings only and does not replace structured outputs.
- `backend/app/workflows/career_workflow.py` is the orchestration layer and uses the existing agent interfaces. A revision loop is capped by `max_revisions` and reruns the owning stage when a verifier finding identifies the owner.
- `backend/app/agents/llm_client.py` uses the Google GenAI client and reads the model from `CAREER_LLM_MODEL` or defaults to `gemini-3.8-flash`; temperature/seed are not explicitly pinned in the code and must therefore be treated as SDK defaults unless Step 18 adds explicit configuration.

## 3. Derived evaluation questions and evidence mapping

The following mapping is the one used for Step 17. It is explicitly derived from the supplied research problem and objective and is not claimed to be the complete thesis proposal.

| Research problem/objective area | Derived evaluation question | Experiment(s) | Metric(s) | Required ground truth / reference | Permissible conclusion |
|---|---|---|---|---|---|
| Career recommendation quality | Does the proposed system recommend careers more effectively than an LLM-only baseline and with traceable evidence? | E2; C1 = F vs B0; C3 = B2 vs B3 | Hit@k, nDCG@k, ranking stability | Human-annotated relevance labels for each profile/career pair, or a documented gold set on the evaluation set | The system is useful for ranked recommendation under the dataset and label policy; not a claim about all real-world graduates |
| Skill-gap analysis grounded in occupational knowledge | Does the system classify skill gaps consistently with the occupational KB and explicit evidence? | E3; E9; secondary B2/B3/F vs B0 | status macro-F1, gap-set precision/recall/F1, over-credit rate | KB-derived required-skill set plus annotated user-skill status labels; valid only when KB validity is itself accepted | Skill-gap status is grounded and consistent with the knowledge base, conditional on E9 |
| Learning roadmap generation | Does the roadmap cover the missing and claimed-only skills without inventing unsupported learning items? | E6 | coverage, grounding, unsupported-item rate | existing skill-gap result and valid learning-resource provenance rules | The roadmap is grounded in the computed gap result and supported by the available knowledge base |
| Verification and traceability | Does the Verification Agent detect unsupported or inconsistent claims and preserve evidence traceability? | E4a, E4b, E5b | unsupported-claim detection rate, resolution rate, traceability level | injected faults + human-audited lineage | The verifier detects unsupported output and maintains an evidence chain, not that it fixes all errors by itself |
| Operational viability | What is the runtime cost and stability of the pipeline? | E5a, E7 | latency, failure rate, token usage, API calls | run logs and manifest metadata | The architecture is operationally feasible under the test harness, not necessarily production-ready |

## 4. Final operational definitions of the four configurations

### B0: LLM-only baseline

B0 is defined as an LLM-only configuration with no Occupational Knowledge Base access and no Verification Agent.

Operational requirements:

- The model receives the user profile text and the 10-career label space only.
- It must not receive the KB `career_skills` relationships, deterministic weight tables, or the system's canonical skill catalog beyond the names the prompt explicitly contains.
- It must not call `compute_career_fit()` or any deterministic skill-gap engine.
- It may perform skill extraction, ranking, and skill-status reasoning internally as part of the model's prompt-driven behavior.
- It must not silently receive OKB data via hidden prompt templates, cached context, or shared preprocessing.

This is a whole-approach baseline for LLM capability, not a neutral baseline for all components.

### B2: LLM with OKB relations, no system scoring

B2 is defined as a configuration in which the LLM receives the occupational relationship information from the OKB, but the matching, scoring, ranking, and skill-gap classification are done by the LLM itself rather than the deterministic engine.

Operational requirements:

- The prompt includes the same canonical skill identifiers and/or names present in the KB relationship set and the same profile bundle as the deterministic system, without exposing internal formulae or weights unless intentionally labelled as an exploratory “formula-given” branch.
- The model is responsible for mapping skill claims to KB skills, ranking careers, and classifying the skill gap.
- It must not call `compute_career_fit()` or `classify_skill_gap()`.
- The prompt must not include algorithmic scoring math unless the run is explicitly identified as a separate exploratory variant.

### B3: system-based pipeline without verification

B3 is the deterministic system pipeline with the OKB and the shared matching/scoring logic enabled, but without the Verification Agent.

Operational requirements:

- Use `retrieval_service` to fetch the occupational context and `compute_career_fit()` for career scoring.
- Use `classify_skill_gap()` in `skill_gap_service.py` for the deterministic skill-gap result.
- Use the real recommendation and skill-gap agents, but disable the independent verification node and revision loop.
- Preserve all other validation that is part of the normal agent stack; do not remove schema checks or business rules solely to make B3 appear simpler.

### F: full system

F is the complete architecture:

- OKB access,
- deterministic career-fit and skill-gap engine,
- recommendation and roadmap generation,
- Verification Agent,
- revision loop bounded by `max_revisions`.

Operational requirements:

- The verification step independently inspects the produced recommendation, skill-gap, and roadmap objects against the canonical KB and the deterministic engines.
- Verification findings are reported, not silently rewritten.
- A failed check may trigger the responsible stage rerun and subsequent verification, subject to the revision cap.

## 5. Comparison validity and claim boundaries

The primary comparison set is:

- C1 = F vs B0
- C2 = F vs B3
- C3 = B2 vs B3

The protocol makes the following claims explicit:

| Comparison | Claim | Limitation |
|---|---|---|
| F vs B0 | Overall benefit of the complete proposed approach over an LLM-only baseline | Cannot attribute the effect to a single component; profile representation and pipeline differ in multiple ways |
| F vs B3 | Effect of Verification Agent detection and revision behavior under controlled conditions | Only valid if the profile bundle, model, KB fingerprint, and non-verifier prompt/config are held constant |
| B2 vs B3 | Effect of LLM-driven vs system-based matching/scoring under equivalent operational information | Only valid when B2 and B3 receive the same relevant KB information and no hidden scoring formula is leaked |

### Controlled variables required for each comparison

- For F vs B3: same user profile bundle, same KB snapshot, same model/provider settings, same prompt versions for all non-verifier steps, and only the verification node / revision loop difference.
- For B2 vs B3: same profile bundle, same canonical career set, same KB relationship set, same filtering rules, and no deterministic formula leakage into the B2 prompt.
- For F vs B0: report as whole-approach comparison, not attribution to a single module; the profile representation and pipeline differ by design.

## 6. Metric selection and evidence requirements

Metrics are selected to support the three core outcomes and the verification/traceability requirement, without inventing unsupported ground truth.

### Primary metrics

- Career ranking: Hit@1, Hit@3, nDCG@3.
- Skill-gap classification: macro-F1 on the four status categories, with a documented reference policy and a provision for missing-OKB cases.
- Verification performance: unsupported-claim detection rate and false-positive rate under controlled fault injection.
- Traceability: percentage of recommendation and gap items with a resolvable KB or user-evidence lineage.

### Secondary metrics

- Pairwise recommendation stability, per-career reasoning-call cost, failure rate, API-call count, latency, token usage.
- Roadmap coverage and grounding metrics against the deterministic skill-gap result.
- Over-credit rate and claimed-only false-match rate when evidence quality is separated by evidence type.

### Interpretation rule

The KB is not treated as an unquestioned gold standard. Skill-gap and recommendation correctness are only interpretable after the knowledge-base validity check (E9) is performed and reported.

## 7. Step boundaries and no-implementation rule

This task completes the design and documentation stage only.

- Step 17: finalize evaluation protocol, dataset and annotation rules, experimental design, reproducibility requirements, and Gate A decisions.
- Step 18: implement the experimental infrastructure, configuration paths, manifests, and reproducible runner code.
- Step 19: validate the infrastructure with automated checks.
- Step 20: run pilot and formal experiments under the approved protocol.

This document does not implement Step 18 and does not run formal experiments.

## 8. Completion status for Step 17

Step 17 is complete only when:

1. The supplied research problem/objective are mapped to derived evaluation questions without redefining the official research framing.
2. The four configurations are defined consistently across the repository documents.
3. Comparison validity and the boundaries of causal claims are made explicit.
4. The Gate A decisions are recorded and the blocking/approval states are documented.
5. The repository paths and file set are consistent with the actual implementation.

No live/paid LLM calls, formal experiments, or database-mutating run configuration are performed in this step.
