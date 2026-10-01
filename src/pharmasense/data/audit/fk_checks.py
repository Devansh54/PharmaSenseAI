"""Foreign key and cross-table consistency checks."""
from typing import Dict, List

import pandas as pd

from pharmasense.contracts import SCHEMAS


def check_foreign_keys(table: str, df: pd.DataFrame, ref_frames: Dict[str, pd.DataFrame]) -> List[Dict]:
    schema = SCHEMAS[table]
    results: List[Dict] = []
    for fk in schema.foreign_keys:
        ref_df = ref_frames[fk.ref_table]
        ref_values = set(ref_df[fk.ref_column].astype(str))

        col_values = df[fk.column].astype(str)
        if fk.nullable:
            checked = col_values[col_values.str.strip() != ""]
        else:
            checked = col_values

        orphans = checked[~checked.isin(ref_values)]
        results.append(
            {
                "table": table,
                "column": fk.column,
                "references": f"{fk.ref_table}.{fk.ref_column}",
                "nullable": fk.nullable,
                "orphan_count": int(len(orphans)),
                "sample_orphan_values": sorted(orphans.unique().tolist())[:10],
                "passed": len(orphans) == 0,
            }
        )
    return results


def check_adverse_event_site_trial_consistency(
    adverse_events: pd.DataFrame, trial_sites: pd.DataFrame
) -> Dict:
    """Verify each AE's site_id actually belongs to the AE's trial_id.

    Stricter than a plain FK check: validates the *combination* of
    trial_id + site_id against the trial_sites mapping table, catching
    cases where both IDs exist independently but are mismatched.
    """
    site_to_trial = dict(
        zip(trial_sites["site_id"].astype(str), trial_sites["trial_id"].astype(str))
    )

    mismatches = []
    for _, row in adverse_events.iterrows():
        event_id = str(row["event_id"])
        trial_id = str(row["trial_id"])
        site_id = str(row["site_id"])
        expected_trial = site_to_trial.get(site_id)
        if expected_trial is None:
            mismatches.append(
                {
                    "event_id": event_id,
                    "trial_id": trial_id,
                    "site_id": site_id,
                    "reason": "site_id not found in trial_sites",
                }
            )
        elif expected_trial != trial_id:
            mismatches.append(
                {
                    "event_id": event_id,
                    "trial_id": trial_id,
                    "site_id": site_id,
                    "reason": f"site belongs to trial {expected_trial}, not {trial_id}",
                }
            )

    return {
        "check": "adverse_event_site_trial_consistency",
        "mismatch_count": len(mismatches),
        "sample_mismatches": mismatches[:20],
        "passed": len(mismatches) == 0,
    }
