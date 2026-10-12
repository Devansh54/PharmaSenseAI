# PharmaSenseAI

**[Open PharmaSenseAI →](https://devansh54.github.io/PharmaSenseAI/)**

Evidence-first pharmaceutical R&D analysis over the supplied synthetic dataset and research documents. Five specialist agents combine structured queries, document retrieval, and cited reports in a Python modular monolith with a React frontend.

For research use only. Not intended for clinical decisions, diagnosis, or emergency monitoring. Compound similarity compares recorded attributes, not molecular structures.

## Capabilities

| Agent | Purpose |
| --- | --- |
| Trial Data Analyst | Analyze trials, enrollment, sites, and laboratory records. |
| Literature Research | Retrieve internal research with traceable source citations. |
| Adverse Event Triage | Classify recorded events and queue qualifying cases for human review. |
| Compound Similarity | Compare compounds by available metadata. |
| Report Writer | Synthesize specialist findings into evidence-backed reports. |

The UI includes a searchable Question Library, evidence inspection, and a human review queue. Workflows use bounded execution, explicit tool permissions, and guardrails for medical advice and prompt injection.

**Stack:** Python 3.11 · FastAPI · LangGraph · PostgreSQL + pgvector · React · TypeScript · Vite

## Run locally

Requires Python 3.11, [uv](https://docs.astral.sh/uv/), Docker Compose, Node.js 22.18+ (for the frontend test runner), and npm.

### Backend

```bash
git clone https://github.com/devansh54/PharmaSenseAI.git
cd PharmaSenseAI
uv sync --locked --all-extras
```

Set the backend environment variables in your terminal. The API currently uses Groq; choose a model available to your account:

```bash
export GROQ_API_KEY="your-api-key"
export PHARMASENSE_LLM_MODEL="your-groq-model-id"
```

The default database URL matches the local Compose service. Set `PHARMASENSE_DATABASE_URL` to use another database. Keep credentials out of version control.

Initialize a fresh local database, load the supplied CSVs, and build the document index:

```bash
docker compose -f deployment/compose.yaml up -d --wait
uv run alembic upgrade head
uv run python -m pharmasense.data.ingest.import_csvs
uv run python -m pharmasense.retrieval.ingestion
uv run uvicorn pharmasense.api.main:app --host 127.0.0.1 --port 8000
```

The ingestion commands replace existing imported records and document chunks; use them for initial setup. The first document ingestion downloads the embedding model.

### Frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. The development server proxies API requests to port 8000; use `VITE_API_BASE_URL` in `frontend/.env` for another backend.

- API documentation: http://127.0.0.1:8000/docs
- Readiness check: http://127.0.0.1:8000/health/ready

## Checks

```bash
# Backend (repository root; database integration tests need PostgreSQL)
uv run pytest

# Frontend (from frontend/)
npm test
npm run lint
npm run build
```

Live provider tests require credentials and may consume tokens. Historical acceptance results are documented separately from current test runs.

## Documentation

- [Architecture and project blueprint](Project%20Architechture%20by%20Astra.md)
- [Development setup](docs/SETUP.md)
- [Data quality and source limitations](docs/DATA_QUALITY.md)
- [Security acceptance](docs/security_acceptance.md)
- [Historical acceptance report](docs/final_acceptance_report.md)
- [Question catalog](evals/question_catalog.json)
