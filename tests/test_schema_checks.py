from phase1.audit.schema_checks import check_schema


def test_all_tables_pass_schema_check(csv_frames):
    for name, df in csv_frames.items():
        result = check_schema(name, df)
        assert result["passed"], result
