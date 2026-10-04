# Tier 1 Validation Readiness & Execution Guide

## Pipeline Repair Status

The master evaluation pipeline has been fully audited and repaired. The following critical issues are resolved:
1. **Gemini Continuation**: Model-generated tool call context and parameters are strictly preserved and coalesced correctly in multi-turn history.
2. **LLMJudge Traceability**: The `LLMJudge` now evaluates using the `LLMGateway` (instead of bypassing it), ensuring that judge calls participate in throttling, structured parsing, and telemetry.
3. **LIVE Mode Enforcement**: The pipeline distinguishes between LIVE and OFFLINE execution without silently falling back to mocked adapters when credentials mismatch or fail.
4. **Telemetry Initialization & Isolation**: The pre-flight checks programmatically invoke Alembic migrations to guarantee the evaluation database (`EVAL_DATABASE_URL`) contains all required telemetry schemas (e.g., `runtime_traces`, `runtime_events`) prior to case execution. Migration targeting is strictly isolated from the development `DATABASE_URL` and verified by regression test.
5. **Robust Pre-Flight**: Execution strictly validates the required API key for the chosen provider, checks database connectivity, ensures schema parity, and enforces rate-limit constraints before beginning execution.

## Execution Requirements

To execute the validated Tier 1 live baseline, the environment must strictly meet the following prerequisites:

### Environment Variables

**Required Parameters (Must be exact):**
* `LLM_PROVIDER`: `gemini`
* `LLM_MODEL`: `gemini-3.5-flash-lite`
* `EVAL_DATABASE_URL`: Must point to the isolated PostgreSQL evaluation database (e.g., `postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test`).
* `GEMINI_API_KEY`: Must be a valid Gemini API key.

**Explicitly Unset/Omitted Variables:**
* `DATABASE_URL`: Do not set this variable in the evaluation shell. The pipeline will isolate itself from the production/development database.
* `OPENAI_API_KEY`, `GROQ_API_KEY`: Should be unset unless intentionally configured for a different run.

### Cache State

The application revision has been bumped to `0.2.1`. The fingerprinting mechanism includes the `APP_VERSION`, ensuring that previous diagnostic test results from `0.2.0` will automatically be bypassed, forcing a clean, untainted run.

## Execution Steps

1. Clear previous diagnostic reports (if necessary) to prevent confusion:
   ```powershell
   rm -ErrorAction SilentlyContinue docs/evaluation_report.md
   ```

2. Export the required variables in your shell (do not commit these):
   ```powershell
   $env:LLM_PROVIDER="gemini"
   $env:LLM_MODEL="gemini-3.5-flash-lite"
   $env:EVAL_DATABASE_URL="postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test"
   # Ensure $env:GEMINI_API_KEY is also set
   ```

3. Run the evaluation script via `uv`:
   ```powershell
   uv run python -m evals.runner
   ```

## Expected Pre-Flight Output

If correctly configured, the evaluation script will output the following exact pre-flight sequence before executing `case 1`:

```
Starting Phase 8 Golden-Set Evaluation...
Running in LIVE mode (Provider: gemini, Model: gemini-3.5-flash-lite).
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
Database schema initialized successfully.
Pre-flight check: Estimating up to 140 API calls (max) for 28 cases.
Pre-flight checks passed.
```

If any prerequisite fails, the run will abort immediately with a `FATAL` log, preventing partial, tainted, or unobservable benchmark data.
