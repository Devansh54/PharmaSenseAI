"""Read-only anomaly detection across the baseline datasets.

None of these checks mutate the source CSVs; they only report findings.
"""
from typing import Dict, List

import pandas as pd


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def anomalies_compounds(df: pd.DataFrame) -> List[Dict]:
    anomalies = []
    tox = _to_num(df["toxicity_score"])
    bad_tox = df[(tox < 0) | (tox > 1)]
    if len(bad_tox):
        anomalies.append(
            {
                "check": "toxicity_score_out_of_range",
                "count": int(len(bad_tox)),
                "sample_ids": bad_tox["compound_id"].head(10).tolist(),
            }
        )

    mw = _to_num(df["molecular_weight_da"])
    bad_mw = df[mw <= 0]
    if len(bad_mw):
        anomalies.append(
            {
                "check": "non_positive_molecular_weight",
                "count": int(len(bad_mw)),
                "sample_ids": bad_mw["compound_id"].head(10).tolist(),
            }
        )
    return anomalies


def anomalies_clinical_trials(df: pd.DataFrame) -> List[Dict]:
    anomalies = []
    start = _to_date(df["start_date"])
    planned = _to_date(df["planned_end_date"])
    actual_end = _to_date(df["actual_end_date"])
    target = _to_num(df["target_enrollment"])
    actual_enr = _to_num(df["actual_enrollment"])

    bad_dates = df[start > planned]
    if len(bad_dates):
        anomalies.append(
            {
                "check": "start_date_after_planned_end_date",
                "count": int(len(bad_dates)),
                "sample_ids": bad_dates["trial_id"].head(10).tolist(),
            }
        )

    bad_actual_end = df[(actual_end.notna()) & (actual_end < start)]
    if len(bad_actual_end):
        anomalies.append(
            {
                "check": "actual_end_date_before_start_date",
                "count": int(len(bad_actual_end)),
                "sample_ids": bad_actual_end["trial_id"].head(10).tolist(),
            }
        )

    over_enrolled = df[actual_enr > target * 1.5]
    if len(over_enrolled):
        anomalies.append(
            {
                "check": "actual_enrollment_exceeds_150pct_of_target",
                "count": int(len(over_enrolled)),
                "sample_ids": over_enrolled["trial_id"].head(10).tolist(),
            }
        )

    completed_no_end = df[(df["status"] == "Completed") & (actual_end.isna())]
    if len(completed_no_end):
        anomalies.append(
            {
                "check": "completed_status_missing_actual_end_date",
                "count": int(len(completed_no_end)),
                "sample_ids": completed_no_end["trial_id"].head(10).tolist(),
            }
        )

    non_terminal_with_end = df[
        (~df["status"].isin(["Completed", "Terminated"])) & (actual_end.notna())
    ]
    if len(non_terminal_with_end):
        anomalies.append(
            {
                "check": "non_terminal_status_has_actual_end_date",
                "count": int(len(non_terminal_with_end)),
                "sample_ids": non_terminal_with_end["trial_id"].head(10).tolist(),
            }
        )

    return anomalies


def anomalies_trial_sites(df: pd.DataFrame) -> List[Dict]:
    anomalies = []
    enrollment = _to_num(df["enrollment_count"])
    negative = df[enrollment < 0]
    if len(negative):
        anomalies.append(
            {
                "check": "negative_enrollment_count",
                "count": int(len(negative)),
                "sample_ids": negative["site_id"].head(10).tolist(),
            }
        )
    return anomalies


def anomalies_lab_results(df: pd.DataFrame) -> List[Dict]:
    anomalies = []
    bad_flag = df[~df["pass_fail"].isin(["Pass", "Fail"])]
    if len(bad_flag):
        anomalies.append(
            {
                "check": "pass_fail_not_in_expected_set",
                "count": int(len(bad_flag)),
                "sample_ids": bad_flag["result_id"].head(10).tolist(),
            }
        )

    val = _to_num(df["result_value"])
    negative = df[val < 0]
    if len(negative):
        anomalies.append(
            {
                "check": "negative_result_value",
                "count": int(len(negative)),
                "sample_ids": negative["result_id"].head(10).tolist(),
            }
        )
    return anomalies


def anomalies_adverse_events(df: pd.DataFrame) -> List[Dict]:
    anomalies = []
    mismatch = df[(df["seriousness"] == "Serious") & (df["severity"] == "Mild")]
    if len(mismatch):
        anomalies.append(
            {
                "check": "serious_seriousness_with_mild_severity",
                "count": int(len(mismatch)),
                "sample_ids": mismatch["event_id"].head(10).tolist(),
            }
        )

    fatal_not_serious = df[(df["outcome"] == "Fatal") & (df["seriousness"] != "Serious")]
    if len(fatal_not_serious):
        anomalies.append(
            {
                "check": "fatal_outcome_not_marked_serious",
                "count": int(len(fatal_not_serious)),
                "sample_ids": fatal_not_serious["event_id"].head(10).tolist(),
            }
        )
    return anomalies


ANOMALY_CHECKS = {
    "compounds": anomalies_compounds,
    "clinical_trials": anomalies_clinical_trials,
    "trial_sites": anomalies_trial_sites,
    "lab_results": anomalies_lab_results,
    "adverse_events": anomalies_adverse_events,
}
