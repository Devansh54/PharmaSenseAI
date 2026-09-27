# Phase 1 Data Quality Methodology

This document describes the read-only audit performed against the 7
baseline CSVs in `pharmasense_synthetic_data_csv/`. The audit never
modifies source files; all findings are written to `phase1/reports/`.

## Checks performed

### 1. Schema and type checks (`phase1/audit/schema_checks.py`)
For each table, validates that the CSV header matches the expected
column list (name and order) and that every non-empty value in a
column matches its declared logical type (str / int / float / date /
datetime / bool).

### 2. Primary key and integrity checks (`phase1/audit/integrity_checks.py`)
- Null primary key values
- Duplicate primary key values
- Full-row duplicates
- Nulls in other required (non-PK) columns

### 3. Foreign key checks (`phase1/audit/fk_checks.py`)

| Table | Column | References | Nullable |
|---|---|---|---|
| clinical_trials | compound_id | compounds.compound_id | no |
| trial_sites | trial_id | clinical_trials.trial_id | no |
| lab_results | compound_id | compounds.compound_id | no |
| adverse_events | trial_id | clinical_trials.trial_id | no |
| adverse_events | site_id | trial_sites.site_id | no |
| research_documents | compound_id | compounds.compound_id | yes |
| research_documents | trial_id | clinical_trials.trial_id | yes |

### 4. Adverse event / site / trial consistency
Beyond the plain FK checks above, each adverse event's `(trial_id,
site_id)` pair is validated against `trial_sites` to confirm the
referenced site actually belongs to the referenced trial -- not just
that both IDs independently exist somewhere in their respective
tables.

### 5. Anomaly detection (`phase1/audit/anomaly_checks.py`, read-only)
Examples of checks performed (findings are reported, not "fixed"):
- `toxicity_score_out_of_range`: compounds.toxicity_score outside [0, 1]
- `non_positive_molecular_weight`: compounds.molecular_weight_da <= 0
- `start_date_after_planned_end_date` (clinical_trials)
- `actual_end_date_before_start_date` (clinical_trials)
- `actual_enrollment_exceeds_150pct_of_target` (clinical_trials)
- `completed_status_missing_actual_end_date` (clinical_trials)
- `non_terminal_status_has_actual_end_date` (clinical_trials)
- `negative_enrollment_count` (trial_sites)
- `pass_fail_not_in_expected_set` (lab_results)
- `negative_result_value` (lab_results)
- `serious_seriousness_with_mild_severity` (adverse_events)
- `fatal_outcome_not_marked_serious` (adverse_events)

## Provenance and drift
`phase1/provenance.py` computes a SHA-256 hash, row count, and column
count for every source CSV and stores a timestamped manifest under
`phase1/provenance/` (plus a `manifest_latest.json` pointer).
`phase1/ingestion/drift.py` compares the current manifest against the
last stored one to flag added, removed, or content-changed files
between ingestion runs.

## Reproducing the audit
```
python -m phase1.audit.run_audit
```
See `phase1/reports/audit_report_latest.md` for a human-readable
summary and `audit_report_latest.json` for the full machine-readable
result (used as CI artifacts).
