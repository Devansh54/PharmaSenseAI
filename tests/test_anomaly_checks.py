from pharmasense.data.audit.anomaly_checks import ANOMALY_CHECKS


def test_anomaly_checks_execute_without_error(csv_frames):
    """Anomaly checks must run cleanly; findings are informational, not
    pass/fail, since anomalies may legitimately exist in the source data.
    """
    for name, fn in ANOMALY_CHECKS.items():
        findings = fn(csv_frames[name])
        assert isinstance(findings, list)
