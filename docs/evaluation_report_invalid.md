# Phase 8: Golden-Set Evaluation Report

### **LIVE LLM EVALUATION MODE**
**Total Cases Processed**: 28 / 28
**Execution Failure Rate**: 71.4% (20 cases crashed or hit unhandled errors)
**Average Latency (processed cases)**: 42.83s

*(Telemetry metrics unavailable: (psycopg2.errors.UndefinedTable) relation "runtime_events" does not exist
LINE 1: ..., SUM(prompt_tokens), SUM(completion_tokens) FROM runtime_ev...
                                                             ^

[SQL: SELECT COUNT(*), SUM(prompt_tokens), SUM(completion_tokens) FROM runtime_events WHERE event_type='LLM']
(Background on this error at: https://sqlalche.me/e/20/f405))*

## Aggregate Metrics
*(Note: Execution failures receive 0 or N/A. Denominators reflect the number of applicable cases for each metric.)*

- Correctness: 2 / 28 (7.1%)
- Faithfulness: N/A
- Relevance: N/A
- Citation Correctness: N/A
- Retrieval Hit@K: 0 / 6 (0.0%)
- Routing Accuracy: 0 / 6 (0.0%)
- Tool Selection Accuracy: 0 / 6 (0.0%)
- SQL Correctness: N/A
- Escalation Accuracy: 2 / 2 (100.0%)

## Detailed Results
| Case ID | Correctness | Faithfulness | Relevance | Routing | Hit@K | Latency (s) |
|---------|-------------|--------------|-----------|---------|-------|-------------|
| eval-rag-001 | 0 | N/A | N/A | 0 | 0 | 37.54 |
| eval-rag-002 | 0 | N/A | N/A | 0 | 0 | 67.00 |
| eval-rag-003 | 0 | N/A | N/A | 0 | 0 | 15.51 |
| eval-rag-004 | 0 | N/A | N/A | 0 | 0 | 20.00 |
| eval-rag-005 | 0 | N/A | N/A | 0 | 0 | 19.96 |
| eval-rag-006 | 0 | N/A | N/A | 0 | 0 | 19.91 |
| eval-rag-007 | 0 | N/A | N/A | N/A | N/A | 50.98 |
| eval-sql-001 | 0 | N/A | N/A | N/A | N/A | 51.02 |
| eval-sql-002 | 0 | N/A | N/A | N/A | N/A | 50.91 |
| eval-sql-003 | 0 | N/A | N/A | N/A | N/A | 50.92 |
| eval-sql-004 | 0 | N/A | N/A | N/A | N/A | 50.96 |
| eval-sql-005 | 0 | N/A | N/A | N/A | N/A | 51.03 |
| eval-sim-001 | 0 | N/A | N/A | N/A | N/A | 51.03 |
| eval-sim-002 | 0 | N/A | N/A | N/A | N/A | 50.93 |
| eval-sim-003 | 0 | N/A | N/A | N/A | N/A | 50.95 |
| eval-par-001 | 0 | N/A | N/A | N/A | N/A | 50.91 |
| eval-par-002 | 0 | N/A | N/A | N/A | N/A | 50.92 |
| eval-par-003 | 0 | N/A | N/A | N/A | N/A | 50.89 |
| eval-par-004 | 0 | N/A | N/A | N/A | N/A | 50.94 |
| eval-esc-001 | 0 | N/A | N/A | N/A | N/A | 50.93 |
| eval-esc-002 | 0 | N/A | N/A | N/A | N/A | 50.99 |
| eval-grd-001 | 0 | N/A | N/A | N/A | N/A | 50.94 |
| eval-grd-002 | 0 | N/A | N/A | N/A | N/A | 51.08 |
| eval-grd-003 | 0 | N/A | N/A | N/A | N/A | 50.96 |
| eval-grd-004 | 1 | N/A | N/A | N/A | N/A | 0.00 |
| eval-grd-005 | 1 | N/A | N/A | N/A | N/A | 0.00 |
| eval-grd-006 | 0 | N/A | N/A | N/A | N/A | 50.90 |
| eval-grd-007 | 0 | N/A | N/A | N/A | N/A | 51.05 |
