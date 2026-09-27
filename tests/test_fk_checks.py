from phase1.audit.fk_checks import (
    check_foreign_keys,
    check_adverse_event_site_trial_consistency,
)
from phase1.schemas import SCHEMAS


def test_foreign_keys_have_no_orphans(csv_frames):
    for name in SCHEMAS:
        if not SCHEMAS[name].foreign_keys:
            continue
        results = check_foreign_keys(name, csv_frames[name], csv_frames)
        for r in results:
            assert r["passed"], r


def test_adverse_event_site_trial_consistency(csv_frames):
    result = check_adverse_event_site_trial_consistency(
        csv_frames["adverse_events"], csv_frames["trial_sites"]
    )
    assert result["passed"], result
