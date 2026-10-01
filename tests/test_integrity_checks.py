from pharmasense.data.audit.integrity_checks import (
    check_primary_key,
    check_required_columns,
    check_full_row_duplicates,
)


def test_primary_keys_unique_and_not_null(csv_frames):
    for name, df in csv_frames.items():
        result = check_primary_key(name, df)
        assert result["passed"], result


def test_required_columns_populated(csv_frames):
    for name, df in csv_frames.items():
        result = check_required_columns(name, df)
        assert result["passed"], result


def test_no_full_row_duplicates(csv_frames):
    for name, df in csv_frames.items():
        result = check_full_row_duplicates(name, df)
        assert result["passed"], result
