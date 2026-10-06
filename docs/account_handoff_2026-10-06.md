# Account Continuation Handoff
**Date**: 2026-10-06

## Repository State
- **Current HEAD Commit**: `1bfbf2c5625405bd640a30e052e61e1e035389bb`
- **Git Status**: Clean. The next account MUST continue directly from this committed repository state without overwriting it.
- **Recent Commits Relevant to PharmaSense**:
  - `1bfbf2c` fix(ae): enforce mandatory serious-event triage steps
  - `819a8dd` fix(ae): implement deterministic serious-event escalation
  - `31d93ac` fix(eval): prevent pytest from wiping eval database during live tests
  - `5a09610` fix(rag): preserve vector evidence in literature research

## Runtime Environment
- **Current Runtime Provider/Model**: Groq, `qwen/qwen3.8-27b`
- **Persistent Eval DB State**: Ready and seeded (`pharmasense_test`)
- **Embedding Model**: `BAAI/bge-small-en-v1.5`
- **Embedding Dimension**: 384

## Acceptance Test Results (S1 - S3)
- **S1 (Clinical Trial Enrollment)**: LIVE PASS
- **S2 (Literature RAG)**: LIVE PASS
- **S3 (Adverse Event Triage)**:
  - **Offline Result**: PASS (174 passed, 1 skipped)
  - **Live Result**: **FAIL**
  - **Exact Prompt**: "A site just reported a serious adverse event for Trial TRL-0034 — triage it."
  - **Final Answer**: None (Failed with `Adverse Event Triage failed: Structured output failed schema validation: 'explanation' is a required property`)
  - **Actual Trial/Event IDs**: AE-00023, AE-00225 (retrieved via SQL)
  - **Severity + Seriousness**: Severe, Serious
  - **SQL Tool Call**: `sql_query_tool(query_id="adverse_events_by_trial", parameters={"trial_id": "TRL-0034"})`
  - **AE Severity Classifier Call**: Not executed
  - **Escalation Notifier Call**: Not executed
  - **Escalation Result**: None
  - **Guardrail Result**: {}
  - **Latency**: 1.47s
  - **Retries/Errors**: `Finalization rejected: Serious AE detected. You MUST call ae_severity_classifier_tool to verify seriousness.` followed by schema validation failures as it exhausted iterations in Synthesis Mode.

## Architecture and Known Issues
- **Current Phase**: We have implemented an offline-tested deterministic sequence enforcement in `BaseAgent` and `AETriageAgent` via the `validate_finalization` hook. The architecture blocks bypass of mandatory tool execution.
- **Unresolved Issue (S3 Live Failure)**: The `Adverse Event Triage` agent executes in `single_tool_mode=True` when invoked by the orchestration graph. After the agent correctly calls the first tool (`sql_query_tool`), `BaseAgent.run()` intercepts it because of `single_tool_mode=True`, prunes the context, strips out all `active_tools`, and forces the agent into Synthesis Mode.
  - As a result, the agent is completely unable to call the newly mandated `ae_severity_classifier_tool` and `escalation_notifier_tool`.
  - The `validate_finalization` hook correctly catches this bypass and rejects the finalization, but the model cannot fix it since its tools have been stripped. It maxes out its 6 iterations and fails.

## Important Lessons Learned (S1-S3)
1. **Live Validation Environment Integrity**: The `EVAL_DATABASE_URL` (`pharmasense_test`) must be strictly isolated from standard offline pytest fixtures. We previously had an issue where `pytest` dropped all tables in the `pharmasense_test` database during standard test execution.
2. **Qwen Instruction Following**: Qwen 3.8-27b on Groq will readily bypass required tools if it feels it has sufficient context (e.g. from the SQL result directly) to output the JSON schema. Mandatory steps (like triage escalation) *must* be deterministically enforced at the agent architecture level (`validate_finalization`), rather than trusting the LLM to follow system prompt instructions.
3. **Graph Orchestration vs Agent Loops**: `single_tool_mode=True` forces agents into Synthesis Mode immediately after one tool execution. This fundamentally breaks multi-step tool requirements (like SQL -> Classifier -> Escalation).

## Exact Next Steps
1. Resolve the `single_tool_mode` conflict so that `AETriageAgent` is allowed to execute multiple tools in sequence without being forced into Synthesis Mode.
2. Re-run the LIVE S3 acceptance test using Qwen.
3. Upon a LIVE PASS for S3, proceed to execute the remaining acceptance cases (S4, S5, S6, S7, S8).

## Environment Setup to Continue
**Important Variables (Names only)**:
- `LLM_PROVIDER`
- `LLM_MODEL`
- `EVAL_DATABASE_URL`
- `ACCEPTANCE_MODE`

**Execution Command for S3 Live**:
```powershell
$env:PYTHONPATH="src"
$env:LLM_PROVIDER="groq"
$env:LLM_MODEL="qwen/qwen3.8-27b"
$env:EVAL_DATABASE_URL="postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test"
$env:ACCEPTANCE_MODE="live"
.\.venv\Scripts\pytest.exe tests/test_live_acceptance.py::test_s3_adverse_event -v --log-cli-level=INFO
```
