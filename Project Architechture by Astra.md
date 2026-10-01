Absolutely bro. I found the **Astra outputs you pasted into the conversation files** and checked the architecture + implementation-plan sections directly.

One important thing first: Astra produced an **earlier 14-phase draft** and then a **later consolidated version**. The later version is the one we should treat as the final plan for your project: **12 implementation phases**, with API + frontend combined and documentation/final regression/demo combined. The later stack decision also uses `BAAI/bge-small-en-v1.5`, not the older `all-MiniLM-L6-v2`. I’m using that later version below rather than mixing the two.

# PharmaSenseAI — Final Architecture

## 1. Core design

PharmaSenseAI is an **R&D analysis application over the supplied dataset and document corpus**.

It is **not**:

* a clinical decision-support product
* an emergency monitoring system
* a molecular-structure search engine

The mandatory engineering principles are:

* Preserve confirmed blueprint requirements.
* Make source-data limitations visible.
* Keep numerical calculations deterministic.
* Keep agent execution bounded.
* Require evidence for factual findings.
* Separate analysis from medical advice.
* Make qualifying adverse-event escalation independent of LLM discretion.
* Prefer one understandable deployment instead of distributed infrastructure.
* Clearly distinguish implemented, tested, and proposed capabilities. 

---

# 2. Five-layer architecture

```text
                         USER
                           │
                           ▼
                ┌────────────────────┐
                │ APPLICATION LAYER  │
                │ Streamlit + FastAPI│
                └─────────┬──────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │ ORCHESTRATION LAYER    │
              │ Router / Planner       │
              │ LangGraph workflow     │
              │ State + fan-out/fan-in  │
              └──────────┬─────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       ┌──────────────┐     ┌────────────────┐
       │ AGENT LAYER  │     │ TOOL LAYER     │
       │ 5 specialists│◄───►│ 6 tools         │
       └──────┬───────┘     └───────┬────────┘
              │                     │
              └──────────┬──────────┘
                         ▼
                ┌──────────────────┐
                │ RETRIEVAL LAYER │
                │ Chunking         │
                │ Embeddings       │
                │ pgvector         │
                │ Evidence         │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ DATA LAYER       │
                │ PostgreSQL       │
                │ source schema    │
                │ app schema       │
                └──────────────────┘
```

These are **logical layers**, not separate microservices. The application remains a modular monolith. 

---

# 3. Data architecture

The supplied dataset has seven tables:

| Table                    |      Rows |
| ------------------------ | --------: |
| `compounds`              |       150 |
| `clinical_trials`        |       110 |
| `trial_sites`            |       375 |
| `lab_results`            |     2,000 |
| `adverse_events`         |       500 |
| `research_documents`     |       250 |
| `agent_interaction_logs` |       400 |
| **Total**                | **3,785** |

The source data must be preserved rather than reshaped to make the application easier.

The application uses two conceptual database namespaces:

```text
source
├── compounds
├── clinical_trials
├── trial_sites
├── lab_results
├── adverse_events
├── research_documents
└── agent_interaction_logs

app
├── dataset_snapshots
├── analysis_runs
├── evidence
├── review_tasks
├── review_decisions
├── spans
├── index_versions
└── document_chunks
```

The supplied interaction logs are **not runtime telemetry**. Actual runtime traces are stored separately. 

### Important dataset constraints

`compounds` has no SMILES, InChI, fingerprints, or molecular structures. Therefore the Compound Similarity capability is **attribute-based**, not molecular-structure similarity.

`lab_results` are associated with compounds, not patients or trials, and their pass/fail criteria are not supplied. The application must therefore avoid inventing clinical laboratory thresholds.

For adverse events, **severity and seriousness are separate fields**. Severe does not automatically mean Serious. A recorded `Serious` event must trigger deterministic escalation regardless of causality or outcome. 

---

# 4. Five specialist agents

Exactly five specialists:

### 1. Trial Data Analyst

Responsibilities:

* Trial summaries
* Site summaries
* Enrollment analysis
* Lab summaries
* Descriptive comparisons

Allowed tool:

```text
sql_query_tool
```

Cannot:

* classify adverse events
* make unsupported clinical interpretations
* make causal claims

### 2. Literature & Document Research

Responsibilities:

* Search `research_documents.full_text`
* Retrieve evidence
* Summarize document-supported findings
* Preserve citations

Allowed tool:

```text
vector_search_tool
```

Cannot:

* invent sources
* perform unapproved external searches

### 3. Adverse Event Triage

Responsibilities:

* Retrieve event records
* Apply deterministic classification
* Explain the recorded severity/seriousness
* Trigger the review workflow

Allowed tools:

```text
sql_query_tool
ae_severity_classifier_tool
```

Cannot:

* diagnose
* recommend treatment
* override deterministic escalation

### 4. Compound Similarity

Responsibilities:

* Calculate attribute-based similarity
* Explain ranking
* Show feature contributions and limitations

Allowed tool:

```text
compound_similarity_tool
```

Cannot:

* claim molecular structural similarity
* claim therapeutic equivalence

### 5. Report Writer

Responsibilities:

* Combine already-validated findings
* Preserve limitations
* Produce the final evidence-backed answer

Allowed tool:

```text
citation_formatter_tool
```

Cannot:

* perform fresh analysis
* access new data
* introduce unsupported conclusions

All five specialists use validated structured outputs, and each has its own instruction document. 

---

# 5. Router / Planner

The Router sits above the specialists.

It produces only:

```text
selected specialists
task descriptions
resolved entities
workflow type
dependencies
execution budgets
```

The graph validates that plan before execution.

It does **not** get unlimited autonomous planning.

The system supports three required workflow patterns:

```text
1. Single
Router
  ↓
Specialist
  ↓
Finalizer


2. Sequential
Router
  ↓
Specialist
  ↓
Report Writer
  ↓
Finalizer


3. Parallel
Router
  ↓
┌───────────────┬────────────────┬─────────────────┐
▼               ▼                ▼                 ▼
Trial        Literature       AE Triage        Similarity
└───────────────┴────────────────┴─────────────────┘
                       ↓
                 Report Writer
                       ↓
                   Finalizer
```

The final architecture permits **up to four independent investigative branches**, followed by Report Writer. It does not permit recursive agent-to-agent delegation or unbounded planning. 

---

# 6. Six tools

The exact tool set is:

```text
1. sql_query_tool
2. vector_search_tool
3. ae_severity_classifier_tool
4. compound_similarity_tool
5. citation_formatter_tool
6. escalation_notifier_tool
```

### `sql_query_tool`

Inputs:

```text
query_id
typed parameters
bounded row_limit
```

Must be read-only.

The baseline architecture recommends a **registered parameterized query catalog**. However, if the actual blueprint explicitly requires generated SQL, that must be implemented rather than quietly replaced with templates. 

### `vector_search_tool`

Uses:

* query text
* approved metadata filters
* bounded `top_k`

Returns:

* ranked chunks
* document references
* scores
* index version

### `ae_severity_classifier_tool`

Deterministic.

It separately handles:

```text
severity
seriousness
missing information
matched rules
review requirement
```

Unknown seriousness must remain **unknown**, not become Non-serious.

### `compound_similarity_tool`

Returns:

```text
overall score
coverage
per-feature contribution
profile version
limitations
```

### `citation_formatter_tool`

Resolves:

```text
claim → evidence IDs → citation object
```

### `escalation_notifier_tool`

Persists a human-review task and optionally performs approved delivery.

Persistence and notification delivery are separate states. 

---

# 7. RAG architecture

The RAG pipeline is:

```text
Verified source text
        ↓
Versioned preprocessing
        ↓
Structure-aware chunking
        ↓
Source/chunk metadata
        ↓
Local embeddings
        ↓
pgvector
        ↓
Retrieval
        ↓
Relevance / coverage checks
        ↓
Context assembly
        ↓
Grounded generation
        ↓
Citation validation
```

The actual RAG corpus is:

```text
research_documents.full_text
```

Metadata is preserved so every retrieved passage can be traced back to its source document. 

### Final selected embedding stack

```text
sentence-transformers
        +
BAAI/bge-small-en-v1.5
        +
PostgreSQL pgvector
```

Astra explicitly selected `BAAI/bge-small-en-v1.5` as the lightweight local retrieval baseline. pgvector uses exact search initially; approximate indexing is only considered after measured performance justifies it.

The project must:

* preserve source references
* support metadata filtering
* detect redundant evidence
* abstain when evidence is insufficient
* prevent silent truncation
* validate citations
* version the embedding/index configuration

The earlier Astra draft experimented with different concrete chunk/model settings, but the later final stack selection is the one to follow. 

---

# 8. Compound similarity

Because the dataset has no molecular structure representation, similarity is:

**attribute-based similarity**

Candidate features come from actual compound fields such as:

```text
chemical_class
therapeutic_area
target_protein
molecular_weight_da
solubility_mg_ml
toxicity_score
```

The system should use:

```text
numeric → scaled distance
categorical → match similarity
set-valued → overlap where genuinely applicable
missing feature → excluded from comparison + lower coverage
```

The output must include both the score and the comparable-feature coverage.

No arbitrary scientific weighting and no molecular-similarity claim. 

---

# 9. Adverse-event escalation

This is one of the most important architectural decisions.

```text
Fetch event
   ↓
Validate classification inputs
   ↓
Apply deterministic versioned rules
   ↓
If seriousness == Serious
   ↓
Persist review task
   ↓
Attempt approved notification
   ↓
Return classification + review state
```

The LLM **explains** the result.

The LLM does **not** decide whether escalation happens.

Important distinctions:

```text
severity ≠ seriousness
unknown ≠ non-serious
persisted ≠ notified
notified ≠ acknowledged
```

Repeated processing must be idempotent so the same event/rule combination does not generate duplicate review tasks. 

---

# 10. Guardrails

Mandatory application-level controls include:

```text
No diagnosis
No individualized treatment advice
No unsupported efficacy claims
No unsupported causality claims
No invented source fields
No invented relationships
No fabricated citations
No silent conversion of missing evidence into an answer
No direct unvalidated model output into application logic
No LLM override of Serious-AE escalation
No pretending incomplete analysis is complete
```

Additional security controls:

* Protect patient/site identifiers before LLM access.
* Screen retrieved text for prompt-injection patterns.
* Validate tool calls.
* Validate model outputs.
* Keep permissions explicit.
* Maintain security acceptance tests.

The detailed specialist security review remains a release gate rather than something Astra claimed was already completed. 

---

# 11. API

Final API boundary:

```text
POST /v1/analyses

GET /v1/evidence/{evidence_id}

GET /v1/reviews

GET /v1/reviews/{review_id}

POST /v1/reviews/{review_id}/decisions

GET /health/live

GET /health/ready
```

The frontend does **not** talk directly to PostgreSQL and does **not** invoke agents directly.

It goes:

```text
Streamlit
   ↓
API client
   ↓
FastAPI
   ↓
Router / Orchestrator
```

The analysis response contains:

```text
request_id
outcome
answer
findings
citations
limitations
branch outcomes
escalation references/status
timing
usage summary
```

No arbitrary SQL endpoint is exposed to the UI/API. 

---

# 12. Observability

Every real runtime request should be traceable with:

```text
request ID
trace/span IDs
agent
tool
model
prompt/workflow/tool versions
dataset/index version
timestamps
latency
input/output tokens
cost
errors
citations
escalation status
retry count
```

Important semantics:

```text
unknown tokens ≠ 0 tokens
intentional abstention ≠ system failure
partial_success ≠ success
empty result ≠ database failure
simulation ≠ real notification
```

The supplied `agent_interaction_logs` table is never treated as runtime truth. 

---

# 13. Final technology stack

| Area                  | Selected                                    |
| --------------------- | ------------------------------------------- |
| Language              | Python 3.11                                 |
| LLM                   | `gpt-4.1-mini` through shared adapter       |
| Orchestration         | LangGraph                                   |
| Contracts             | Pydantic                                    |
| Database              | PostgreSQL                                  |
| Data access           | SQLAlchemy + psycopg + Alembic              |
| Vector store          | pgvector                                    |
| Embeddings            | `BAAI/bge-small-en-v1.5`                    |
| Ingestion             | pandas + openpyxl                           |
| Backend               | FastAPI                                     |
| Frontend              | Streamlit                                   |
| Evaluation            | pytest + project-specific golden-set runner |
| Observability         | Structured JSON logs + runtime tables       |
| Packaging             | Docker Compose                              |
| Dependency management | `pyproject.toml` + `uv.lock`                |

Astra explicitly says **do not initially add**:

```text
Redis
Celery
Kubernetes
another agent framework
separate vector database
Ragas
LangSmith
reranking infrastructure
```

Those are not needed for the baseline solo-developer architecture.

---

# 14. Final repository structure

This is Astra's planned repository tree:

```text
PharmaSenseAI/
├── README.md
├── agentic_genai_project_guide.pdf
├── pharmasense_synthetic_data_csv.zip
├── pharmasense_synthetic_dataset.xlsx
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── .dockerignore
├── .env.example
├── alembic.ini
│
├── config/
│   ├── source_mapping.json
│   ├── query_catalog.json
│   ├── ae_rules.json
│   ├── similarity_profile.json
│   ├── rag.json
│   └── model_prices.json
│
├── docs/
│   ├── requirements.md
│   ├── dataset_dictionary.md
│   ├── data_quality.md
│   ├── architecture.md
│   ├── decisions.md
│   ├── security_acceptance.md
│   ├── runbook.md
│   ├── demo.md
│   └── traceability.csv
│
├── src/pharmasense/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── bootstrap.py
│   ├── contracts.py
│   ├── errors.py
│   │
│   ├── db/
│   │   ├── session.py
│   │   ├── models.py
│   │   ├── source_schema.py
│   │   └── repositories.py
│   │
│   ├── data/
│   │   ├── audit.py
│   │   ├── ingest.py
│   │   └── provenance.py
│   │
│   ├── llm/
│   │   ├── client.py
│   │   └── openai_client.py
│   │
│   ├── retrieval/
│   │   ├── text.py
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── index.py
│   │   └── search.py
│   │
│   ├── tools/
│   │   ├── contracts.py
│   │   ├── registry.py
│   │   ├── sql_query.py
│   │   ├── vector_search.py
│   │   ├── ae_classifier.py
│   │   ├── compound_similarity.py
│   │   ├── citations.py
│   │   └── escalation_notifier.py
│   │
│   ├── agents/
│   │   ├── base.py
│   │   ├── trial.py
│   │   ├── literature.py
│   │   ├── adverse_event.py
│   │   ├── similarity.py
│   │   └── report.py
│   │
│   ├── orchestration/
│   │   ├── state.py
│   │   ├── planner.py
│   │   ├── graph.py
│   │   └── finalizer.py
│   │
│   ├── escalation/
│   │   ├── rules.py
│   │   └── service.py
│   │
│   ├── validation/
│   │   ├── requests.py
│   │   ├── outputs.py
│   │   ├── evidence.py
│   │   └── policy.py
│   │
│   ├── observability/
│   │   ├── logging.py
│   │   ├── tracing.py
│   │   └── usage.py
│   │
│   ├── api/
│   │   ├── app.py
│   │   ├── schemas.py
│   │   ├── dependencies.py
│   │   └── routes/
│   │
│   └── ui/
│       ├── app.py
│       ├── api_client.py
│       └── views/
│
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── evals/
│   ├── golden_set.jsonl
│   ├── retrieval_labels.jsonl
│   ├── rubrics.json
│   ├── metrics.py
│   └── runner.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── acceptance/
│
└── deployment/
    ├── Dockerfile.api
    ├── Dockerfile.ui
    ├── compose.yaml
    └── smoke_check.py
```

Runtime-generated things go under ignored `artifacts/`, `.cache/`, `.venv/`, and `.env`. 

---

# 15. Implementation plan — FINAL 12 PHASES

This is the later consolidated roadmap Astra produced.

## Phase 1 — Data Foundation

**Objective:** build a reproducible, queryable representation of the dataset.

Tasks:

* audit CSVs
* verify relationships
* document anomalies
* transactionally import all seven tables
* record source hashes
* establish provenance
* test repeatability

Main files:

```text
data/audit.py
data/ingest.py
data/entities.py
db/models.py
db/session.py
db/repositories.py
migrations/
docs/data_quality.md
```

Dependencies:

```text
pandas
openpyxl
PostgreSQL
SQLAlchemy
psycopg
Alembic
Pydantic
```

Tests:

```text
counts
schemas
nulls
duplicate keys
orphan references
cross-table consistency
rollback
repeatability
```

**Done when:** the machine-generated audit reconciles with the actual source and ingestion does not silently alter facts. 

---

## Phase 2 — Shared LLM Gateway

**Objective:** centralize all LLM access.

Implement:

```text
provider-independent interface
OpenAI adapter
structured output handling
tool calling
timeouts
bounded transient retries
usage accounting
```

Files:

```text
llm/client.py
llm/openai_client.py
contracts.py
config.py
errors.py
observability/usage.py
observability/tracing.py
```

Tests:

```text
mocked responses
tool-call parsing
invalid outputs
timeouts
missing usage
cost calculation
```

**Done when:** every future agent can use the same gateway and no agent directly calls the provider. 

---

## Phase 3 — RAG Foundation

**Objective:** retrieve citable evidence from `research_documents`.

Implement:

```text
document preprocessing
structure-aware chunking
embeddings
pgvector indexing
metadata filters
redundancy handling
source references
index/model versioning
```

Files:

```text
retrieval/chunking.py
retrieval/embeddings.py
retrieval/index.py
retrieval/search.py
config/rag.json
```

Tests:

```text
short docs
long docs
chunk limits
metadata filters
source references
duplicates
empty results
index compatibility
retrieval baseline
```

**Done when:** every source document is accounted for, retrieval returns resolvable evidence, and there is no silent truncation. 

---

## Phase 4 — Tested Tool Library

Implement all six tools **before agent integration**.

```text
SQL
Vector search
AE classification
Compound similarity
Citation formatter
Escalation notifier
```

Tests must cover:

```text
known records
input validation
query correctness
similarity calculations
citation resolution
idempotent escalation
explicit failures
```

Source data remains read-only during analysis. 

---

## Phase 5 — Specialist Agents

Build:

```text
Trial Data Analyst
Literature & Document Research
Adverse Event Triage
Compound Similarity
Report Writer
```

Also create:

```text
agent_specs/<agent_name>/instructions.md
```

Each specialist instruction document is approximately **500–1,500 words** and includes:

* scope
* allowed tools
* outputs
* refusal rules
* escalation rules
* examples

Tests cover tool permissions, evidence references, refusal behavior, invalid output handling, and execution budgets. 

---

## Phase 6 — Router + Orchestration

Implement:

```text
intent planning
entity resolution
dependency validation
single-agent workflow
sequential workflow
parallel fan-out/fan-in
finalization
```

Tests:

```text
routing
single execution
sequential ordering
actual parallelism
deadlines
cancellation
partial failures
escalation preservation
```

No unbounded planning loop. 

---

## Phase 7 — Guardrails

Complete:

```text
request validation
output validation
evidence validation
medical-advice boundaries
identifier protection
prompt-injection screening
SQL/tool acceptance
security acceptance
```

Every required guardrail must map to an implementation control and a test.

Do not mark security as complete while specialist security acceptance is unfinished. 

---

## Phase 8 — Golden-Set Evaluation

Use the specified **28-case golden set**.

Measure:

```text
correctness
faithfulness
relevance
citation correctness
retrieval quality
routing
tool selection
SQL correctness
escalation
latency
tokens
cost
failure rate
```

Files:

```text
evals/golden_set.jsonl
retrieval_labels.jsonl
rubrics.json
runner.py
metrics.py
docs/evaluation_report.md
```

The report must contain **actual results**, not anticipated performance. 

---

## Phase 9 — Observability Completion

Complete runtime telemetry:

```text
request/trace IDs
agent spans
tool spans
model usage
cost
latency
citations
escalations
errors
```

Test:

```text
trace completeness
concurrent-request isolation
usage aggregation
unknown-cost handling
error semantics
escalation semantics
```

The goal is that a request can be reconstructed from operational metadata without relying on hidden model reasoning. 

---

## Phase 10 — API + Frontend

### FastAPI

Expose:

```text
POST /v1/analyses
GET /v1/evidence/{id}
GET /v1/reviews
GET /v1/reviews/{id}
POST /v1/reviews/{id}/decisions
GET /health/live
GET /health/ready
```

### Streamlit

Views:

```text
analysis
evidence
reviews
```

The UI communicates only through the API. 

---

## Phase 11 — Portable Deployment

Use:

```text
Dockerfile.api
Dockerfile.ui
compose.yaml
smoke_check.py
```

Architecture:

```text
Browser
   ↓
Streamlit container
   ↓
FastAPI container
   ├── Router
   ├── Agents
   ├── Tools
   ├── Validation
   ├── Local embedding model
   └── Hosted LLM
            ↓
     PostgreSQL + pgvector
            ↓
     Persistent volume
```

Agents do **not** become separate containers.

Initialization:

```text
migrations
→ data import
→ document index
→ compatibility check
→ smoke tests
→ start application
```

No re-embedding on every restart/request.  

---

## Phase 12 — Documentation + Final Regression + Demo

Finalize:

```text
ARCHITECTURE.md
docs/decisions.md
docs/demo.md
docs/talking_points.md
docs/traceability.csv
docs/evaluation_report.md
README.md
```

Then run:

```text
full regression
documentation smoke tests
specialist demo coverage
requirement-evidence review
```

Final deliverable must have concrete evidence for every mandatory requirement and must clearly disclose limitations. 

---

# 16. Exact execution order Astra recommends

The dependency-minimizing sequence is:

```text
1. Freeze source interpretation + contracts
2. Establish database correctness
3. Establish LLM gateway + telemetry
4. Build retrieval + deterministic tools
5. Validate specialists individually
6. Integrate orchestration
7. Complete guardrail acceptance
8. Measure and correct behavior
9. Complete observability
10. Build API/UI on stable contracts
11. Package deployment
12. Finalize documentation + demo
```

The core principle is:

```text
Audit
 ↓
Contracts
 ↓
Database
 ↓
LLM Gateway
 ↓
RAG
 ↓
Tools
 ↓
Specialists
 ↓
Orchestration
 ↓
Application
```

That order is specifically designed to minimize rework for a solo developer.

# 17. P0 / P1 / P2 priorities

### P0 — Must have

```text
Dataset audit
Seven-table ingestion
Shared LLM adapter
RAG + citations
Six tools
Five agents
Router
Three orchestration patterns
Deterministic Serious-AE escalation
Attribute-based similarity
Guardrails
Security acceptance
Golden-set evaluation
Observability
Usable API/application
Portable local demo
Architecture/documentation/demo artifacts
```

### P1

```text
Backup/restore automation
UI polish
Richer charts
Feedback collection
External escalation delivery
```

### P2

```text
Cloud deployment
Reranking/hybrid retrieval
Structural chemistry enrichment
Distributed execution
Microservices
```

Astra explicitly recommends completing P0 before spending time on P1/P2.

---

# 18. Testing strategy

Testing is requirement-driven, not just code-coverage-driven.

```text
Data validation
        ↓
Ingestion
        ↓
SQL tools
        ↓
Lab analysis
        ↓
AE rules
        ↓
Escalation
        ↓
Similarity
        ↓
RAG
        ↓
Agents
        ↓
Orchestration
        ↓
Application safety
        ↓
Security
        ↓
Observability
        ↓
API/UI
        ↓
Deployment
```

Three major execution modes:

```text
Fast unit tests
→ mocked/deterministic

Integration tests
→ real PostgreSQL + pgvector

Live evaluation
→ explicit opt-in + controlled budget

Golden-set regression
→ 28 cases + independently established expected results
```

Reproducibility requirements include pinning dataset/index versions, fixing the time reference for relative-date questions, separating adversarial fixtures, independently calculating similarity references, and testing actual concurrency rather than assuming it.

---

# 19. What Astra explicitly does NOT want us to build

This is important for you because you're working alone.

```text
❌ Dataiku requirement
❌ Snowflake requirement
❌ Kubernetes
❌ Redis
❌ Celery
❌ Separate vector database
❌ Microservice-per-agent architecture
❌ Autonomous recursive agent loops
❌ Real clinical monitoring
❌ Full clinical case-management system
❌ Molecular similarity without molecular structures
❌ Extra statistics agent
❌ Treating simulated interaction logs as runtime truth
❌ Blindly inventing dataset relationships
```

The architecture is deliberately a **modular monolith** so that you can actually understand, test, defend, and demonstrate the whole system.  

---

## The architecture in one sentence

> **PharmaSenseAI is a bounded, evidence-first, five-agent R&D analysis system built as a Python modular monolith with FastAPI + Streamlit, PostgreSQL + pgvector, a shared `gpt-4.1-mini` gateway, deterministic tools/guardrails, LangGraph orchestration, citable RAG over `research_documents.full_text`, measured evaluation, and persisted observability.**

That is the architecture/implementation direction we should use for the rest of your project. 

**And for your current state:** you are already past Phase 1 and Phase 2, and you're currently fixing the existing **Phase 3 RAG foundation** branch. So we should **not restart this architecture or rebuild earlier phases**; the next work is to finish Phase 3 according to this plan. 
