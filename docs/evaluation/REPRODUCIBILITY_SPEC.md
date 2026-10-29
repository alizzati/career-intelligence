# Reproducibility Specification

Status: Step 17 design, no model-backed execution.

## 1. Goal

The evaluation framework must make the experiments auditable and repeatable enough to support thesis-level interpretation. The repository already provides the main architecture and deterministic components; the reproducibility specification focuses on the missing metadata and run isolation required before Step 18.

## 2. Implementation-grounded facts from the repository

The current LLM client is configured in `backend/app/agents/llm_client.py`.

Relevant facts:

- The provider is the Google GenAI SDK.
- The configured model comes from `CAREER_LLM_MODEL`, otherwise it defaults to `gemini-3.8-flash`.
- The API key is read from `GEMINI_API_KEY`.
- `complete_json()` calls `generate_content()` with a JSON response mime type and `max_output_tokens`.
- Temperature, top-p, top-k, and random seed are not explicitly set in the current client implementation.

This means the system currently exposes model identity and max token length, but not an explicit seeded inference configuration. The evaluation protocol therefore treats those parameters as SDK defaults unless Step 18 adds explicit pinning.

## 3. Required run manifest

Each experiment run must record:

- config id (`B0`, `B2`, `B3`, `F`)
- dataset version
- annotation version
- dataset split
- profile id and profile hash
- model identifier and provider
- prompt version or prompt hash
- OKB version or KB fingerprint
- code revision and working-tree state
- run timestamp
- environment and branch identifier
- output artifact path or run ID
- failure/retry metadata, timeout, and parser errors

The repository currently does not contain the `analysis_id` / logging tables described in `MASTER_SPEC.md`. Therefore, Step 18 must create the run-manifest persistence required by the protocol; until then, the evaluation design documents the expected fields but not their implementation.

## 4. Model and inference pinning

The protocol requires that the model choice and inference setting be pinned and recorded before any scientific claim is made.

Recommended operational definition:

- Model: record exact model string and provider version at the time of the run.
- Prompt version: store a hash of the exact prompt text or the prompt file used.
- Inference parameters: record any explicit values set in the client or config; if they are not set, record the SDK default and the fact that no explicit pinning occurs.
- Random seed: if the backend or provider does not support a seed, report that as unsupported and proceed with a default-setting record.

This is a Step 18 requirement if the implementation does not yet expose a seeded configuration in `llm_client.py`.

## 5. Knowledge-base versioning

The OKB is a foundational input to the evaluation. The protocol requires a KB fingerprint or content version for each run.

Minimum fields:

- KB snapshot identifier
- source dataset name or import job ID
- import timestamp
- hash or manifest of the imported KB tables
- status of whether the KB was unchanged across runs

The repository includes a proof of a guarded validation process and inspection metadata, but no production-grade versioning table is present yet. This is a Step 18 implementation requirement.

## 6. Database and isolation strategy

The evaluation pipeline must isolate experimental runs from the local development database.

Required design:

- use a separate runtime/test database for evaluation batches
- avoid mutating the primary project database during pilot or formal experiments
- store synthetic or system-generated users in a dedicated experiment namespace or database
- ensure the verification and workflow outputs are captured in a separate artifact store and not mixed with the main app state

This is consistent with the repository’s Step 16 guarded validation approach and with the broader research requirement to keep experimental execution reproducible and isolated.

## 7. Failure handling and missing outputs

The reproducibility specification requires explicit handling of the following:

- provider timeout
- quota or rate limit errors
- invalid JSON response
- empty or incomplete output
- missing prompt or artifact file
- mismatch between expected and actual run counts

Each failure must be logged with:

- config id
- step name
- stage or agent
- exception type
- request and retry count
- whether the system fell back to a deterministic template

The system already does this at a limited level for workflow failure logging; Step 18 must formalize the same approach into experiment manifests.

## 8. Privacy, redaction, and sensitive data handling

The project already includes a PII redaction boundary and best-effort redaction logic.

Required for reproducibility:

- store only redacted CV text or a redacted profile representation, not the original raw text, for LLM-facing calls
- log the redaction version and whether redaction was applied
- keep an audit trail linking the input profile, redacted output, and downstream structured user profile
- never treat CV text extracted from files as a permanently retained raw artifact in the workflow state

This is consistent with the repository's privacy-preserving design and must remain in force for all experiments.

## 9. Step 18 implementation requirement

This Step 17 document defines what must be implemented in Step 18:

- explicit configuration schema for model, prompt, and KB version
- run manifest persistence
- experiment database separation
- output and failure artifact storage
- redaction and manifest audit trails
- a fixed seed or a documented inability to provide one

No live or paid model call is executed during Step 17.
