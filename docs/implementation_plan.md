# Implementation Plan

## 1. Current Project Status
- **Repository State:** The repository contains an early implementation partitioned into `phase1/`, `phase2/`, and `phase3/` directories rather than a consolidated `src/pharmasense/` package.
- **Git Branch:** Currently on `phase3-rag-foundation`.
- **Dependency Management:** Has a `requirements.txt` but no `pyproject.toml` or `uv.lock`.
- **Database:** PostgreSQL migrations exist for Phase 1 and Phase 3 (RAG pgvector).

## 2. Completed Phases
- **Phase 1 (Data Foundation):** Mostly complete (in `phase1/`), but code is not in `src/`.
- **Phase 2 (Shared LLM Gateway):** Mostly complete (in `phase2/`), but code is not in `src/`.

## 3. Current Active Phase
- **Phase 0 (Refactoring & Modernization):** ✅ Complete. Codebase unified into `src/pharmasense/`, `uv` dependency management active, tests pass.
- **Phase 3 (RAG Foundation):** ✅ Complete. PostgreSQL + pgvector container active, schemas migrated, base data and RAG embeddings ingested, and all DB integration tests pass successfully.

## 4. Remaining Phases
- **Phase 4 (Tested Tool Library):** ✅ Complete. Implemented 6 deterministic core tools, added Review tables, achieved >90% test coverage.
- **Phase 5 (Specialist Agents):** ✅ Complete. Built 5 bounded agents on the Phase 2 LLM Gateway with strict per-agent tool registries.
- **Phase 6 (Router + Orchestration):** ✅ Complete. Implemented stateful router, single/sequential/parallel LangGraph workflows, explicit fan-in boundaries, and strict validation.
- Phase 7: Guardrails
- Phase 8: Golden-Set Evaluation
- Phase 9: Observability Completion
- Phase 10: API + Frontend
- Phase 11: Portable Deployment
- Phase 12: Documentation + Final Regression + Demo

## 5. Architecture Gaps
- The project structure currently splits concerns by phase (e.g., `phase1.config`, `phase3.config`) instead of domain (e.g., `pharmasense.db`, `pharmasense.retrieval`).
- Lacks `uv` dependency setup.

## 6. Code Gaps
- Shared configurations need to be unified.
- Missing `src/pharmasense` integration.
- Tests need updating to point to the new `src/pharmasense/` paths.

## 7. Structural/Refactoring Changes
- Move `phase1/`, `phase2/`, `phase3/` logic into `src/pharmasense/`.
- Unify `alembic/` and migrations into the root `migrations/` folder as specified by Astra.
- Consolidate tests into a standard `tests/` tree.

## 8. Dependency Changes
- Replace `requirements.txt` with `pyproject.toml` using `uv`.
- Pin `Python 3.11`.
- Generate `uv.lock`.

## 9. Required Configuration/Environment Changes
- Centralize `config.py` in `src/pharmasense/`.
- Provide a clear `.env.example`.

## 10. Database/Migration Changes
- Move existing alembic setup to the root as `migrations/`.
- Ensure migrations apply cleanly on the new structure.

## 11. Test Changes
- Refactor all `test_*.py` files in `tests/` to import from `pharmasense.*` instead of `phase1.*`, `phase2.*`, `phase3.*`.
- Re-run all tests to ensure zero regressions.

## 12. Documentation Changes
- Create `docs/architecture.md`.
- Keep this `docs/implementation_plan.md` updated.

## 13. Exact Implementation Order
1. Create `pyproject.toml` and `.python-version`. Run `uv sync`.
2. Restructure: move code from `phase*` folders to `src/pharmasense/` domain folders.
3. Update Alembic/Migrations path.
4. Refactor tests to import from `src/pharmasense`.
5. Run tests, fix any breakages from imports.
6. Commit structural refactor.
7. Proceed to Phase 4 (Tested Tool Library).

## 14. Risks and Blockers
- **Risk:** Unifying `config.py` from different phases might cause conflicts if they rely on disjoint env vars or schemas.
- **Risk:** Migration history might be tied to specific phase modules. Need to ensure `env.py` points to the unified `Base`.
- **Blocker:** Postgres DB setup is required to run tests. Docker Compose needs to be verified for local DB access.

## 15. Definition of Done for each phase
- **Phase 0:** `uv` is configured, structure matches `src/pharmasense/`, all previous tests pass.
- **Phase 3:** RAG foundation fully tested against DB, tests pass under new structure.
