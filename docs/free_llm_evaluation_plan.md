# Free-Only Multi-LLM Evaluation and Improvement Plan

## 1. Objective
To systematically evaluate, diagnose, and improve the PharmaSenseAI system across multiple free-tier LLM providers without incurring API costs. The workflow will use the existing 28-case Phase 8 evaluation framework, employing exhaustive caching, deduplication, and pre-flight quota estimation to strictly adhere to free-tier provider limits.

## 2. Verified Free-Model Ladder (Candidate Ordering)
This ladder proceeds from an experimental lightweight to a high-capability candidate model, utilizing only strictly free APIs from Groq and Google Gemini based on currently available models that support tool calling and JSON structured outputs. The exact capability ranking is not an established fact; the evaluation results will determine the empirical ranking.

1. **Tier 1 (Fast/Small, Baseline):** `gemini-3.5-flash-lite` (Google Gemini)
2. **Tier 2 (Balanced Open-Weight):** `qwen/qwen3.8-27b` (Groq)
3. **Tier 3 (Mid-Range Capable):** `openai/gpt-oss-20b` (Groq)
4. **Tier 4 (High Capability/Speed):** `gemini-3.8-flash` (Google Gemini)
5. **Tier 5 (Maximum Reasoning/Large):** `openai/gpt-oss-120b` (Groq)

*Note: Models such as `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`, and older Groq models have been excluded in favor of the most current, highest-performing free tier endpoints that support the complex tool interactions required by the RAG workflow.*

## 3. Provider/Model Capability Matrix
| Provider | Model ID | Tool Calling | Structured Output | Context | Est. Free-Tier Limit |
|----------|----------|--------------|-------------------|---------|----------------------|
| Gemini | `gemini-3.5-flash-lite` | Yes | Yes (JSON) | 1,048,576 | Project/model-specific; verify current limits in Google AI Studio before benchmark. |
| Groq | `qwen/qwen3.8-27b` | Yes | Yes (JSON) | 131,042 | ~30 RPM, 1,000 RPD on Free Plan. |
| Groq | `openai/gpt-oss-20b` | Yes | Yes (JSON) | 131,072 | ~30 RPM, 1,000 RPD on Free Plan. |
| Gemini | `gemini-3.8-flash` | Yes | Yes (JSON) | 1M | Project/model-specific; verify current limits in Google AI Studio before benchmark. |
| Groq | `openai/gpt-oss-120b` | Yes | Yes (JSON) | 131,072 | ~30 RPM, 1,000 RPD on Free Plan. |

*Note: Free-tier limits are shared at the project/organization level. Heavy tool-calling chains consume multiple requests per case.*

## 4. Required Architecture Changes
*   **LLM Gateway Extension:** A new `GroqAdapter` must be created in `src/pharmasense/llm/groq_adapter.py` (the `GeminiAdapter` is implemented).
*   **Configuration:** The Gateway must support `LLM_PROVIDER=groq` and `LLM_PROVIDER=gemini` seamlessly, mapping models dynamically.
*   **Database Isolation:** Use an explicit `EVAL_DATABASE_URL` environment variable to connect to the evaluation database, avoiding hacky rewrites of the primary `DATABASE_URL`.
*   **No Agent Logic Changes:** The orchestration and specialist agents must remain completely provider-agnostic. All provider logic sits behind the Gateway.

## 5. Evaluation Workflow and Safety Gates
1.  **Selective Execution:** Do not automatically run every model. Pick the target model for the specific experiment.
2.  **Smoke Test First:** Perform exactly one live network smoke test before triggering a benchmark run for any model.
3.  **Pre-Flight Quota Estimation:** Before execution, perform a conservative pre-flight budget check using the best currently known/configured provider limits. If the estimated run cannot safely fit within those limits, abort before starting the benchmark. Runtime 429/quota responses must still be handled safely because provider limits may vary or change.
4.  **Paced Execution:** For runs that fit daily limits but exceed RPM limits, inject sleep delays between cases. Never intentionally exceed limits.

## 6. Comprehensive Run Deduplication and Caching
Every completed case must be resumable and deduplicated. Caches must be hyper-specific to prevent false positives during systemic improvements.

**A. Evaluation Fingerprint Cache (Skips previously completed cases):**
The cache key must combine:
- `provider`
- `model`
- `case_id`
- `application_version` (code version)
- `prompt_config_version`
- `tool_definition_version`
- `rag_data_version` (must refer to a reproducible/immutable dataset snapshot or database state)
- `generation_settings` (temperature, max_tokens)
- `judge_configuration_version`

**B. Judge Caching (Skips redundant LLM-as-judge calls):**
The judge cache key must combine:
- `report_hash` (SHA-256 of the generated report text)
- `judge_provider`
- `judge_model`
- `judge_prompt_version`
- `rubric_version`

## 7. Experiment and Versioning Strategy
1.  **Targeted Diagnosis:** Do not repeatedly rerun full 28-case suites during development. If a bug is found in routing, rerun only the affected routing cases for the targeted model.
2.  **Systemic Changes:** If a prompt or tool definition changes, bump the `prompt_config_version`. This automatically invalidates the Evaluation Fingerprint Cache for all models, forcing a fresh run only for the cases that are actually evaluated next.
3.  **Final Validation:** A final, full 28-case evaluation is required *only* for the final selected system configuration to certify baseline-vs-improved performance.

## 8. Definition of Done
1. `GroqAdapter` implemented cleanly.
2. `evals/runner.py` completely retrofitted with pre-flight quota checks and hyper-specific fingerprint/judge caching.
3. Explicit `EVAL_DATABASE_URL` routing is confirmed.
4. Model ladder and metrics tracking accurately log the specific versions and models defined above.

## 9. Blockers / Required Approvals
No architectural blockers. Live benchmark execution remains gated on successful smoke testing and verification of current provider/model free-tier limits.
