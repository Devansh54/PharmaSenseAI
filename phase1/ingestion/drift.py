"""Drift detection: compare current CSV state against last recorded provenance.

Usage:
    python -m phase1.ingestion.drift
"""
import json
from typing import Dict, List

from phase1.provenance import build_manifest, load_latest_manifest


def detect_drift() -> Dict:
    previous = load_latest_manifest()
    current = build_manifest()

    if not previous:
        return {
            "baseline_exists": False,
            "message": "No previous provenance manifest found; this run establishes the baseline.",
            "current_manifest_captured_at": current["captured_at"],
        }

    drift_findings: List[Dict] = []
    prev_files = previous.get("files", {})
    curr_files = current.get("files", {})

    for name in sorted(set(prev_files) | set(curr_files)):
        prev_meta = prev_files.get(name)
        curr_meta = curr_files.get(name)

        if prev_meta is None:
            drift_findings.append({"file": name, "change": "added_since_baseline"})
            continue
        if curr_meta is None:
            drift_findings.append({"file": name, "change": "missing_since_baseline"})
            continue
        if prev_meta.get("sha256") != curr_meta.get("sha256"):
            drift_findings.append(
                {
                    "file": name,
                    "change": "content_changed",
                    "previous_sha256": prev_meta.get("sha256"),
                    "current_sha256": curr_meta.get("sha256"),
                    "previous_row_count": prev_meta.get("row_count"),
                    "current_row_count": curr_meta.get("row_count"),
                }
            )

    return {
        "baseline_exists": True,
        "baseline_captured_at": previous.get("captured_at"),
        "current_captured_at": current.get("captured_at"),
        "drift_detected": len(drift_findings) > 0,
        "findings": drift_findings,
    }


if __name__ == "__main__":
    print(json.dumps(detect_drift(), indent=2))
