# Tier 1 Offline Diagnosis Report

## 1. Observed Failure
During the Phase 8 Tier 1 Baseline evaluation using `gemini-3.5-flash-lite`, the system exhibited a **0.0% Routing Accuracy** and **0.0% Tool Selection Accuracy**. The orchestration completely bypassed all specialist agents (Trial Data Analyst, Literature Research, etc.) and instead defaulted to the escalation/fallback path (Escalation Accuracy: 92.9%), running at an abnormally fast latency of ~0.22s per case.

## 2. Evidence from the Baseline / Cache
- **Run Cache (`evals/.cache/run_cache.json`)**: All RAG, SQL, Paraphrase, and Simulation cases failed `correctness` with average latencies ~0.2s. Hit@K metrics were mostly `N/A`, confirming the retrieval agents were never invoked.
- **Estimated API Calls**: The pre-flight check estimated ~140 calls, but the actual execution completed near-instantly with only ~28 requests, proving the multi-step agent loop exited on Step 1.

## 3. Exact Failure Location in the Pipeline
The failure occurs inside the LangGraph workflow at the `PlannerNode` (`src/pharmasense/orchestration/planner.py`), specifically when attempting to invoke the LLM via the `LLMGateway`. The failure causes `PlannerNode` to catch an exception and return `{"errors": [...]}`. The `route_after_planner` conditional edge in `src/pharmasense/orchestration/graph.py` detects this error and immediately routes the graph to the `finalizer` node, bypassing all specialists.

## 4. Root-Cause Candidates
- **A. Gemini model capability**: The model is unable to follow the structured format.
- **B. Router prompt/instruction design**: Poor instructions led to malformed generation.
- **C. Tool/schema/structured-output incompatibility**: The JSON schema is rejected by the API.
- **D. GeminiAdapter ↔ LLMGateway response mapping**: Adapter dropped tool calls.
- **E. LangGraph/router integration**: Graph routed incorrectly.
- **F. Fallback/error-handling behavior**: Exceptions are silently swallowed.
- **G. Request construction issues**: Empty `contents` or invalid model names.

## 5. Evidence For/Against Each Candidate
- **Against A (Capability) & B (Prompt)**: The model never had the chance to generate a response. The API rejected the request before generation began.
- **Against D (Adapter Mapping) & E (Graph Integration)**: The smoke tests verified that the adapter correctly formats Gemini tool calls and the gateway integrates smoothly. The graph routed correctly given the error state it received.
- **For C (Schema Incompatibility)**: `Plan.model_json_schema()` uses Pydantic to generate a JSON Schema containing keys like `additionalProperties` and `title`. The Gemini free-tier API explicitly rejects `additionalProperties` (only supported in Enterprise mode).
- **For F (Fallback Behavior)**: `PlannerNode` blindly catches `Exception` and returns it as `{"errors": [...]}`. The graph treats any error state as an immediate trigger to route to `finalizer`, masking the underlying SDK exceptions.
- **For G (Request Construction)**:
  - `PlannerNode` sends the prompt as a single `Message(role="system")`. The `GeminiAdapter` correctly extracts system messages for the `system_instruction` config parameter, leaving the main `contents` array empty. Gemini SDK throws `ValueError: contents are required`.
  - `PlannerNode` hardcodes `model="gpt-4.1-mini"` in the `LLMRequest`, which is passed to the API.

## 6. Most Likely Root Cause
The failure is **not** a Gemini model limitation. It is caused by three compounding architectural defects in `PlannerNode`:
1. **Empty Message Payload**: Sending only a `system` message results in an empty `contents` array for Gemini, throwing a client-side validation error.
2. **Schema Incompatibility**: Pydantic's JSON schema injects unsupported fields (like `additionalProperties`) which the free-tier Gemini API rejects.
3. **Hardcoded Model**: `PlannerNode` hardcodes `"gpt-4.1-mini"`, bypassing the gateway's configured provider model.

Because `PlannerNode` catches all exceptions and silently delegates to the `finalizer`, these fatal errors resulted in 0% routing instead of crashing the runner.

## 7. Recommended Fix
1. **Fix Payload Construction**: Update `PlannerNode` to pass the prompt as a `user` message (or split it into `system` instructions + a `user` message containing the input prompt).
2. **Fix Schema Generation**: In `PlannerNode`, sanitize the Pydantic schema before passing it to `response_schema` by recursively popping unsupported keys (`additionalProperties`, `title`, `default`).
3. **Fix Hardcoded Model**: Remove `model="gpt-4.1-mini"` from the `LLMRequest` in `planner.py`. Allow it to default to `None` or explicitly pull from configuration so the Gateway uses the currently configured tier model.

## 8. Alternative Fixes and Tradeoffs
- **Alternative for Schema**: Switch from `response_schema` (JSON mode) to strict `tools` (Function Calling mode).
  - *Tradeoff*: Requires restructuring the Planner's `Plan` extraction logic, but function calling schemas are often natively handled better by adapters than arbitrary JSON schema constraints.
- **Alternative for Empty Payload**: Modify `GeminiAdapter` to treat a lone `system` message as a `user` message if no other messages exist.
  - *Tradeoff*: Violates LLM messaging paradigms. Fixing the `PlannerNode` to correctly separate system instructions and user input is strictly superior.

## 9. Files Needing Modification
- `src/pharmasense/orchestration/planner.py` (Core fixes for messages, model, and schema sanitization).
- `src/pharmasense/llm/validation.py` or a new utility (To house reusable schema-sanitization logic).

## 10. Exact Tests to Add Before Rerunning Tier 1
- `test_planner_respects_provider_model`: Verify `PlannerNode` does not hardcode an OpenAI model name.
- `test_planner_includes_user_message`: Verify `PlannerNode` emits at least one `user` message.
- `test_planner_schema_sanitization`: Verify the schema passed to `LLMRequest` does not contain `additionalProperties` or other provider-hostile keys.
- `test_gemini_adapter_rejects_empty_contents_gracefully`: Ensure the adapter provides clear context if `contents` evaluates to empty.

## 11. Cache / Version Implications
- **Application Version**: These are code fixes, so `APP_VERSION` should be bumped to ensure tracking.
- **Judge / Data Cache**: The underlying dataset and rubrics are unchanged. Cache will miss organically because the `case_id`s failed correctness before, but since `runner.py` only caches completed valid cases or bypasses failed ones on retry boundaries, a fresh run with the fixed planner will naturally overwrite or bypass the previous failures. (Note: Ensure we don't accidentally skip cases that failed previously if the runner cache logic considers an `escalation` as a successfully completed, albeit incorrect, case. The cache must be cleared manually or `prompt_version`/code footprint updated to force invalidation).
