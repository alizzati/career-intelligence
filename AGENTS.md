# AGENTS.md — Career Intelligence System

## 1. Project Context

This repository contains a thesis project that develops a hybrid, verified multi-agent Career Intelligence System for IT graduates in Indonesia.

The system supports:

1. Career recommendation.
2. Skill-gap analysis.
3. Personalized learning roadmap generation.
4. Verification of consistency and knowledge grounding.

The system uses an Occupational Knowledge Base grounded in available occupational and competency sources, such as KBJI, SKKNI, and IndoTask, depending on the data actually available in the repository.

## 2. Working Principles

* Inspect the existing codebase, tests, documentation, and Git status before making changes.
* Treat the existing implementation and approved project decisions as the source of truth.
* Do not assume a component is missing just because it is not mentioned in the latest prompt.
* Do not recreate, duplicate, or replace working components without a demonstrated reason.
* Implement one development stage at a time. Do not automatically proceed to the next stage.
* Keep changes minimal and limited to files necessary for the requested task.
* If a requirement conflicts with existing architecture or project decisions, explain the conflict before making a consequential change.
* Do not claim that tests pass unless they have actually been executed.

## 3. System Architecture

The intended component flow is:

1. Occupational Knowledge Base and deterministic retrieval.
2. User competency profile representation.
3. Profile Agent.
4. Career Recommendation Agent.
5. Deterministic Skill-Gap Engine and Skill-Gap Agent.
6. Learning Roadmap Agent.
7. Verification Agent.
8. Multi-agent orchestration.
9. API integration.
10. Frontend integration.
11. Evaluation, baseline comparison, and ablation studies.

Use the existing implementation and project documentation to determine the actual completion status of each stage. This sequence is a guide, not permission to skip an unfinished dependency.

## 4. Architectural Rules

* The Occupational Knowledge Base is the grounding source for occupational requirements and supported skill information.
* Use deterministic logic for calculations and structured decisions wherever the existing architecture requires it.
* LLMs may interpret information and generate explanations, but must not override deterministic results or invent unsupported facts.
* Reuse existing schemas, services, interfaces, and canonical identifiers.
* `app/services/career_fit_service.py::compute_career_fit()` is the single source of truth for career-fit calculations. Do not create a competing implementation.
* The Skill-Gap Agent must use the existing Skill-Gap Engine rather than independently recalculating skill gaps.
* The Learning Roadmap Agent must use the skill-gap results as its input. It must not independently recalculate career fit or skill gaps.
* Preserve evidence traceability and distinguish supported skills from unsupported user claims according to the existing implementation.
* Do not invent occupational requirements, learning resources, prerequisites, proficiency levels, or knowledge-base records.

## 5. Skill-Gap Constraints

Preserve the established skill-gap categories:

* Matched — Evidenced
* Matched — Claimed Only
* Missing
* Unmatched User Claim

Do not introduce priority scores, priority tiers, or additional ranking logic unless explicitly approved in the project requirements.

Do not reinterpret unmatched user claims as missing required skills. Preserve the existing meaning of each category and its corresponding schema.

## 6. LLM and Configuration

* Reuse the existing LLM client and its established interface.
* Do not change the LLM provider, model, API client, or `llm_client.py` unless explicitly requested or a demonstrated blocker requires it.
* Do not hardcode API keys, credentials, or other secrets.
* Keep deterministic outputs and the existing fallback behavior when an LLM call fails.
* Validate generated structured output against the applicable schemas and knowledge-base constraints.

## 6.1 Frozen Research Decisions

These decisions supersede conflicting requirements in earlier planning prompts:

* Support exactly the 10 canonical careers in the existing Occupational Knowledge Base.
* `compute_career_fit()` is the single source of truth for career-fit scores.
* Step 9 is deterministic and defines the authoritative skill-gap result.
* Preserve exactly four skill-gap categories: `matched_evidenced`, `matched_claimed_only`, `missing`, and `unmatched_user_claims`.
* Do not introduce skill-gap priority scores, priority tiers, or required-proficiency gap calculations.
* A user claim without evidence is not automatically a missing skill. An unmatched user claim is not a missing career requirement.
* Step 10 explains deterministic skill-gap results but cannot modify them.
* Step 11 generates a learning roadmap from the existing skill-gap results. It must not recalculate career fit or skill gaps.
* Step 12 must report verification findings explicitly and must not silently rewrite source outputs.
* Reuse the existing LLM client and provider. Never assume Gemini or Anthropic without inspecting the active implementation.

Do not restore superseded design choices from earlier prompts unless the researcher explicitly approves the change.

## 6.2 Verification and Orchestration

* Prefer deterministic validation for canonical IDs, career-skill relationships, score consistency, schema validity, and roadmap coverage.
* Validate provenance only against source records that actually exist in the Knowledge Base.
* Distinguish `PASS`, `FAIL`, and `REVISE` according to the implemented verification schema.
* Never silently replace or mutate agent outputs. Preserve the original result and record validation findings.
* Any revision loop must have a configurable maximum attempt count and terminate safely.
* Only revise the component responsible for a failed check. Re-run verification after a revision.
* Do not implement orchestration until the Verification Agent and its tests are complete.
* Do not claim end-to-end workflow support until it has been implemented and tested.


## 7. Testing and Validation

For every implementation task:

1. Inspect relevant unit tests, smoke tests, and regression tests.
2. Add or update tests for the behavior being changed.
3. Run the relevant tests using the project's existing test setup.
4. Run affected regression tests for previously completed components.
5. Report the exact commands executed and their actual results.
6. Explicitly report any tests that could not be executed.

Do not modify tests merely to hide a genuine implementation defect.

## 8. Scope Control

Before implementing a task:

1. Identify the requested component and its dependencies.
2. Check whether the component already exists and is complete.
3. Identify the smallest necessary changes.
4. Implement only the requested stage.
5. Validate the result before proposing the next stage.

Do not silently change database schemas, public interfaces, established data contracts, or completed components.

If a substantial architectural change appears necessary, explain why and wait for approval before proceeding.

## 9. Required Completion Report

After each task, report concisely:

* Existing implementation and gaps found.
* Files created or modified.
* Behavior implemented or corrected.
* Tests executed and actual results.
* Remaining limitations or unresolved issues.
* The next planned stage, without implementing it automatically.

Maintain project continuity through the repository's documentation, source code, tests, and Git history. Do not rely solely on conversation memory or assumptions.

## 10. Project Documentation

* `docs/MASTER_SPEC.md` contains the original project requirements and research objectives.
* `docs/PROJECT_STATE.md` contains the current implementation status.
* Follow the frozen decisions in this `AGENTS.md` when the original master specification conflicts with later approved implementation decisions.
* Read the relevant documentation before making architectural changes.
