"""Executable Phase 1 audit runner.

Usage:
    python -m pharmasense.data.audit.run_audit

This script is strictly read-only with respect to the source CSVs. It
writes its findings to phase1/reports/.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd

from pharmasense.config import CSV_FILES, REPORTS_DIR
from pharmasense.data.audit.schema_checks import check_schema
from pharmasense.data.audit.integrity_checks import (
    check_primary_key,
    check_required_columns,
    check_full_row_duplicates,
)
from pharmasense.data.audit.fk_checks import (
    check_foreign_keys,
    check_adverse_event_site_trial_consistency,
)
from pharmasense.data.audit.anomaly_checks import ANOMALY_CHECKS
from pharmasense.contracts import LOAD_ORDER


def load_dataframes() -> Dict[str, pd.DataFrame]:
    frames = {}
    for name in LOAD_ORDER:
        frames[name] = pd.read_csv(CSV_FILES[name], dtype=str, keep_default_na=False)
    return frames


def run_audit() -> Dict:
    frames = load_dataframes()
    report: Dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "cross_table_checks": [],
        "anomalies": {},
        "summary": {},
    }

    all_passed = True

    for name, df in frames.items():
        table_report = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "schema": check_schema(name, df),
            "primary_key": check_primary_key(name, df),
            "required_columns": check_required_columns(name, df),
            "full_row_duplicates": check_full_row_duplicates(name, df),
            "foreign_keys": check_foreign_keys(name, df, frames),
        }
        report["tables"][name] = table_report

        table_passed = (
            table_report["schema"]["passed"]
            and table_report["primary_key"]["passed"]
            and table_report["required_columns"]["passed"]
            and table_report["full_row_duplicates"]["passed"]
            and all(fk["passed"] for fk in table_report["foreign_keys"])
        )
        if not table_passed:
            all_passed = False

        anomaly_fn = ANOMALY_CHECKS.get(name)
        if anomaly_fn:
            report["anomalies"][name] = anomaly_fn(df)

    ae_site_check = check_adverse_event_site_trial_consistency(
        frames["adverse_events"], frames["trial_sites"]
    )
    report["cross_table_checks"].append(ae_site_check)
    if not ae_site_check["passed"]:
        all_passed = False

    report["summary"] = {
        "all_checks_passed": all_passed,
        "tables_audited": list(frames.keys()),
    }
    return report


def render_markdown(report: Dict) -> str:
    lines = [
        "# PharmaSense Phase 1 Audit Report",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        f"**Overall result:** {'PASSED' if report['summary']['all_checks_passed'] else 'FAILED'}",
        "",
    ]
    for name, table_report in report["tables"].items():
        lines.append(f"## {name} ({table_report['row_count']} rows, {table_report['column_count']} cols)")
        lines.append(f"- Schema check passed: {table_report['schema']['passed']}")
        lines.append(f"- Primary key check passed: {table_report['primary_key']['passed']}")
        lines.append(f"- Required column check passed: {table_report['required_columns']['passed']}")
        lines.append(f"- Full-row duplicate check passed: {table_report['full_row_duplicates']['passed']}")
        for fk in table_report["foreign_keys"]:
            lines.append(
                f"- FK {fk['column']} -> {fk['references']} passed: {fk['passed']} "
                f"(orphans: {fk['orphan_count']})"
            )
        anomalies = report["anomalies"].get(name, [])
        if anomalies:
            lines.append(f"- Anomalies detected: {len(anomalies)}")
            for a in anomalies:
                lines.append(f"  - {a['check']}: {a['count']}")
        lines.append("")

    lines.append("## Cross-table checks")
    for c in report["cross_table_checks"]:
        lines.append(f"- {c['check']} passed: {c['passed']} (mismatches: {c['mismatch_count']})")

    return "\n".join(lines)


def write_report(report: Dict, out_dir: Path = REPORTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"audit_report_{timestamp}.json"
    with open(json_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    latest_json = out_dir / "audit_report_latest.json"
    with open(latest_json, "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    latest_md = out_dir / "audit_report_latest.md"
    with open(latest_md, "w") as fh:
        fh.write(render_markdown(report))

    return json_path


if __name__ == "__main__":
    rep = run_audit()
    path = write_report(rep)
    print(f"Audit report written to {path}")
    print(f"Overall result: {'PASSED' if rep['summary']['all_checks_passed'] else 'FAILED'}")
