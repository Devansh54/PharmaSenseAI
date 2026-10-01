"""Primary key, duplicate, and required-column null checks."""
from typing import Dict

import pandas as pd

from pharmasense.contracts import SCHEMAS


def check_primary_key(table: str, df: pd.DataFrame) -> Dict:
    schema = SCHEMAS[table]
    pk = schema.primary_key
    null_pk_count = int((df[pk].astype(str).str.strip() == "").sum())
    duplicate_mask = df[pk].duplicated(keep=False)
    duplicate_values = sorted(df.loc[duplicate_mask, pk].astype(str).unique().tolist())

    return {
        "table": table,
        "primary_key": pk,
        "null_primary_key_count": null_pk_count,
        "duplicate_primary_key_count": int(duplicate_mask.sum()),
        "duplicate_primary_key_values": duplicate_values[:20],
        "passed": null_pk_count == 0 and int(duplicate_mask.sum()) == 0,
    }


def check_required_columns(table: str, df: pd.DataFrame) -> Dict:
    schema = SCHEMAS[table]
    findings = []
    for col in schema.required_columns:
        if col not in df.columns:
            findings.append({"column": col, "error": "column missing"})
            continue
        null_count = int((df[col].astype(str).str.strip() == "").sum())
        if null_count:
            findings.append({"column": col, "null_count": null_count})
    return {
        "table": table,
        "required_column_findings": findings,
        "passed": len(findings) == 0,
    }


def check_full_row_duplicates(table: str, df: pd.DataFrame) -> Dict:
    dup_count = int(df.duplicated(keep=False).sum())
    return {
        "table": table,
        "duplicate_full_row_count": dup_count,
        "passed": dup_count == 0,
    }
