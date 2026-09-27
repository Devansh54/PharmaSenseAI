# Phase 1 Setup Guide

## Prerequisites
- Python 3.11+
- PostgreSQL 14+ (a local instance, or the `postgres:16` service used in CI)

## 1. Install dependencies
```
pip install -r requirements.txt
```

## 2. Configure the database connection
```
export PHARMASENSE_DATABASE_URL="postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense"
```

## 3. Apply migrations
```
python -m alembic -c alembic.ini upgrade head
```
This creates the 7 source tables plus `data_provenance` and
`ingestion_runs` metadata tables, with foreign keys enforced at the
database level.

## 4. Run the transactional import
```
python -m phase1.ingestion.import_csvs
```
Truncates and reloads all 7 source tables inside a single transaction.
If any table fails to load, the entire import rolls back and the
database is left in its prior state. A provenance manifest is written
to `phase1/provenance/` on success.

## 5. Run the audit
```
python -m phase1.audit.run_audit
```
Writes `phase1/reports/audit_report_latest.json` and `.md`. This is
read-only with respect to the source CSVs.

## 6. Check for drift
```
python -m phase1.ingestion.drift
```
Compares the current CSVs against the last captured provenance
manifest in `phase1/provenance/manifest_latest.json` and reports any
added/removed/changed files.

## 7. Run tests
```
pytest tests/
```
Ingestion/drift integration tests connect to PostgreSQL and are
skipped automatically if no instance is reachable. Schema/PK/FK/
anomaly/provenance tests run against the CSVs directly and require no
database.

## CI
`.gitlab-ci.yml` runs the full sequence above (migrate -> import ->
audit -> drift -> test) against a `postgres:16` service container on
every push, so ingestion and DB-backed tests are exercised in an
environment with a real, reachable database.
