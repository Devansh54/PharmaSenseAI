"""Schema and logical dtype validation for the baseline CSVs."""
from typing import Dict, List

import pandas as pd

from phase1.schemas import SCHEMAS, TableSchema


def check_schema(table: str, df: pd.DataFrame) -> Dict:
    schema: TableSchema = SCHEMAS[table]
    expected_cols = list(schema.columns.keys())
    actual_cols = list(df.columns)

    missing = [c for c in expected_cols if c not in actual_cols]
    extra = [c for c in actual_cols if c not in expected_cols]
    order_matches = actual_cols == expected_cols

    dtype_issues: List[Dict] = []
    for col, kind in schema.columns.items():
        if col not in df.columns:
            continue
        dtype_issues.extend(_check_column_kind(df, col, kind))

    return {
        "table": table,
        "missing_columns": missing,
        "extra_columns": extra,
        "column_order_matches": order_matches,
        "dtype_issues": dtype_issues,
        "passed": not missing and not extra and not dtype_issues,
    }


def _check_column_kind(df: pd.DataFrame, col: str, kind: str) -> List[Dict]:
    issues: List[Dict] = []
    series = df[col].astype(str)
    non_null = series[series.str.strip() != ""]

    if kind == "int":
        bad = non_null[~non_null.str.match(r"^-?\d+$")]
    elif kind == "float":
        bad = non_null[pd.to_numeric(non_null, errors="coerce").isna()]
    elif kind in ("date", "datetime"):
        bad = non_null[pd.to_datetime(non_null, errors="coerce").isna()]
    elif kind == "bool":
        bad = non_null[~non_null.str.lower().isin(["true", "false"])]
    else:  # str
        bad = pd.Series([], dtype=str)

    if len(bad) > 0:
        issues.append(
            {
                "column": col,
                "expected_kind": kind,
                "invalid_row_count": int(len(bad)),
                "sample_invalid_values": bad.head(5).tolist(),
            }
        )
    return issues
