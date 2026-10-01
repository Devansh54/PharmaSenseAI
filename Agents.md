# Agents.md

## 1. Project Purpose
PharmaSenseAI is an R&D analysis application over the supplied dataset and document corpus. It is designed to be an evidence-first, five-agent R&D analysis system built as a Python modular monolith. It is not a clinical decision-support product, emergency monitoring system, or molecular-structure search engine.

## 2. Architecture Source of Truth
The primary source of truth for the architecture, required tools, workflow, and structure is `Project Architechture by Astra.md`.

## 3. Repository Source-of-Truth Rules
The actual repository state (code, branches, and tests) is the source of truth for what is actually implemented. Do not blindly copy documentation; always verify against the real code and Git state.

## 4. Development Workflow
- ANALYZE → PLAN → MODIFY → TEST → REVIEW DIFF → FIX → TEST AGAIN → DOCUMENT → COMMIT.
- Keep changes minimal and architecture-aligned. 
- Ensure incremental progress: one phase at a time.

## 5. Current Phase Workflow
Identify the actual active phase from the repository state. If a phase is partially completed (e.g., Phase 3 RAG Foundation), continue from it. Do not restart completed work. Maintain the Phase Implementation Plan in `docs/implementation_plan.md`.

## 6. Rules for Analyzing Existing Code Before Editing
Never assume the repository is empty. Check `git status`, `git log`, read files, and verify with tests before modifying any file. Run tests to confirm the current state.

## 7. Rules Against Unnecessary Rewrites
Do not rewrite working components merely to match a theoretical file tree unless the structural change materially improves architecture and maintainability (e.g., replacing disjoint phase directories with a unified `src/` layout). Fix only what is necessary to reach the architecture requirements.

## 8. Rules for Preserving Existing Working Functionality
Ensure tests pass after modifications. Update all affected imports, tests, CI workflows, and configs when restructuring. Do not remove functionality without a documented reason.

## 9. Rules for Handling Ambiguity
Make the smallest justified engineering decision and document it, unless it's a destructive change, requires external access, conflicts with source-of-truth, or has major architectural consequences. If blocked by one of those reasons, ask the user.

## 10. What Agents Must Ask the User Before Proceeding
- Destructive data/code changes
- Need for external credentials
- Conflicting source-of-truth requirements
- Resolving genuine requirement ambiguity

## 11. What Agents May Decide Autonomously
- Small engineering decisions for maintainability (e.g., standardizing imports, fixing linting)
- Appropriate standard naming conventions
- How to structure the code within the established architecture

## 12. What Agents Must Never Assume
- Do not invent source-data fields, relationships, or clinical thresholds.
- Do not assume missing information implies a safe default (e.g., unknown seriousness != non-serious).
- Do not assume interaction logs are runtime truth.

## 13. Git Workflow
- Create logical branches for new phases or major changes.
- Check current uncommitted changes. Do not discard uncommitted user work.
- Do not force push or hard reset unless explicitly necessary.

## 14. Commit Conventions
Use Conventional Commits (e.g., `feat:`, `fix:`, `refactor:`, `docs:`).

## 15. Branch Conventions
Branches should map to phases or logical units of work (e.g., `phase3-rag-foundation`). Don't duplicate existing valid branches.

## 16. Testing Requirements
Add/update tests along with implementation. Tests must pass before declaring a phase complete. Types of tests include fast mock-based unit tests, integration tests against Postgres, live evals, and golden-set regressions.

## 17. Dependency-Management Rules
Maintain `pyproject.toml` and a valid committed `uv.lock`. Do not maintain competing dependency lists.

## 18. `uv` Usage
Use `uv run`, `uv sync`, and `uv pip` for virtual environments and dependency management.

## 19. Python Version Conventions
Use Python 3.11 as specified in the architecture plan. Use `.python-version` file.

## 20. Environment/Secrets Rules
Never commit secrets, `.env`, virtual environments, caches, or large runtime outputs.

## 21. Database Migration Rules
Use Alembic for migrations. Preserve existing working migrations.

## 22. API Conventions
The frontend goes through FastAPI. Ensure RESTful guidelines are met. No arbitrary SQL endpoints exposed.

## 23. Agent/Tool Implementation Conventions
- Keep tool permissions explicit.
- Use structured outputs.
- Keep agent execution bounded. Do not allow recursive delegation or unbounded planning.

## 24. Naming Conventions
Use clear, industry-standard names. Avoid overly generic terms or preserving poor legacy naming.

## 25. Folder/File Naming Conventions
Use `snake_case` for Python files and modules. Follow standard modular monolith structures under `src/pharmasense/`.

## 26. Documentation Conventions
Keep documentation in sync with actual code behavior. Update `README.md` and `docs/` as necessary. Maintain an architecture document (`docs/architecture.md`).

## 27. Error-Handling Conventions
Fail safely and transparently. Use appropriate HTTP codes in FastAPI.

## 28. Logging/Observability Conventions
Keep operational telemetry robust. Log request/trace IDs, agent/tool spans, token usages, and citations.

## 29. Security Rules
- Protect patient/site identifiers before LLM access.
- Guard against prompt injection.
- Validate tool inputs and model outputs.

## 30. RAG/Evidence/Citation Rules
- Keep metadata intact to trace back to source documents.
- Abstain when evidence is insufficient.
- No fabricated citations.

## 31. Dataset Integrity Rules
Treat source data as immutable facts. Do not reshape data just to simplify the application.

## 32. Code Quality Rules
- Validate model and tool outputs using typed contracts (Pydantic).
- Implement explicit boundaries and modular separation.

## 33. Definition-of-Done Rules
A phase is complete when:
- Code implements the requirements.
- Tests (unit/integration) pass.
- No architectural violations remain.
- Documentation accurately reflects reality.
- Git working tree is committed with clear messages.
