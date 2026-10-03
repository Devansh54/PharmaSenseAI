# Setup & Development Workflow

This document outlines the standard developer workflow for running tests and bringing up the local database for PharmaSenseAI.

## 1. Environment Setup

Ensure you have [uv](https://docs.astral.sh/uv/) installed.

Install the project dependencies and create the virtual environment:
```bash
uv sync --all-extras
```

## 2. Database Infrastructure

Start the local PostgreSQL + `pgvector` container:
```bash
docker compose -f deployment/compose.yaml up -d --wait
```

## 3. Database Initialization

With the database running, apply the Alembic schema migrations:
```bash
uv run alembic upgrade head
```

## 4. Data & RAG Ingestion

Load the base CSV data and populate the RAG vector store:
```bash
# 1. Ingest base tables
uv run python -m pharmasense.data.ingest.import_csvs

# 2. Ingest document chunks and embeddings
uv run python -m pharmasense.retrieval.ingestion
```

## 5. Testing

Run the full test suite to confirm everything is working, including the database integration tests:
```bash
uv run pytest
```

## Stopping the Database

To stop the database and clean up the container:
```bash
docker compose -f deployment/compose.yaml down
```

To stop and permanently wipe the volume data (requires a fresh ingestion):
```bash
docker compose -f deployment/compose.yaml down -v
```
