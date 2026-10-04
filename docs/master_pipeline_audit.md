# Master Pipeline Audit and Repair

## 1. Provider Contract Audit
* **Finding**: `gpt-4.1-mini` was hardcoded in `src/pharmasense/validation/evidence.py`, causing provider leakage during testing.
* **Fix**: Replaced hardcoded model with `DEFAULT_MODEL` from `config.py`.
* **Regression Coverage**: `DEFAULT_MODEL` ensures any LLM provider selected at runtime will be correctly propagated to all safety and output guardrails.

## 2. Gateway Bypass Correction
* **Finding**: The Evaluator `LLMJudge` (in `evals/runner.py`) was initializing directly against `self.adapter` (e.g. `GeminiAdapter`), completely bypassing `LLMGateway`. This bypassed retries, rate-limiting, observability, and structured-output schema validation parsing.
* **Fix**: Passed `self.gateway` instead of `self.adapter` to `LLMJudge` initialization.
* **Regression Coverage**: All LLM queries now route through `LLMGateway` (Single-Point of Entry).

## 3. Tool Schema Compilation & Validation
* **Finding**: When Gemini generates structured outputs that fail validation against the JSON schema, the `LLMGateway` correctly caught the `LLMInvalidOutputError` and raised an `LLMGatewayError`. However, `BaseAgent` and `PlannerNode` did not safely catch this error.
* **Fix**:
  * Modified `BaseAgent.run` loop to catch `LLMGatewayError` (for failed JSON validation) and `RuntimeError` (for empty responses). If caught, the error is fed back to the LLM as a user message: `Your previous response was invalid. Error: {error_str}. Please correct it...`. This enables auto-correction via retry up to `max_iterations`.
  * Modified `PlannerNode.__call__` to catch `LLMGatewayError` and gracefully return a validation error instead of crashing the agent workflow entirely.
* **Regression Coverage**: Agent logic now successfully degrades gracefully on malformed LLM schemas instead of throwing an unhandled exception.

## 4. Unhandled Exception Propagation (The `_translate_error` defect)
* **Finding**: When an unhandled provider error or validation error occurred (e.g., `LLMGatewayError`), `BaseAgent` attempted to call `self.llm._translate_error(e)` to convert the exception. Because `self.llm` was `LLMGateway`, and `LLMGateway` did not implement `_translate_error`, the script crashed with an `AttributeError` instead of gracefully terminating. This was the direct cause of the 19 crashed cases in the Tier 1 baseline.
* **Fix**: Added `_translate_error(self, exc)` to `LLMGateway` which safely delegates to `self._provider._translate_error`.
* **Regression Coverage**: Pipeline will now properly bubble errors as readable agent state `errors` (e.g. `Trial Data Analyst failed: API timeout`) instead of crashing the core framework.

## 5. Offline Simulation
* **Finding**: Built an offline execution suite `scratch/test_offline_pipeline.py` using `DummyAdapter` to verify the execution loop across all specialists, parsing logic, gateway schema validation, and guardrails.
* **Result**: Tested the workflow of "Input Guardrail -> Planner -> Trial Data Analyst -> Report Writer -> Output Guardrail" completely offline, verifying proper parsing and schema compliance end-to-end.

## Final Status
All integration, contract, and measurement defects preventing valid benchmark results have been identified and patched. The system correctly implements multi-turn continuation, structured parsing, graceful failure retries, and generic error bubbling.
