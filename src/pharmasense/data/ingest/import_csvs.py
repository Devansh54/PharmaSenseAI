"""Transactional import of the 7 baseline CSVs into PostgreSQL.

The entire import runs inside a single database transaction: if any table
fails to load, all changes (including the truncation step) are rolled
back and the database is left in its prior state. Source CSVs are only
ever read, never modified.

Usage:
    python -m pharmasense.data.ingest.import_csvs
"""
import json
from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from pharmasense.config import CSV_FILES, DATABASE_URL
from pharmasense.contracts import SCHEMAS, LOAD_ORDER
from pharmasense.data.provenance import build_manifest, write_manifest


def _coerce_dataframe(table: str, df: pd.DataFrame) -> pd.DataFrame:
    schema = SCHEMAS[table]
    out = df.copy()
    for col, kind in schema.columns.items():
        if col not in out.columns:
            continue
        out[col] = out[col].replace("", pd.NA)
        if kind == "int":
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
        elif kind == "float":
            out[col] = pd.to_numeric(out[col], errors="coerce")
        elif kind in ("date", "datetime"):
            out[col] = pd.to_datetime(out[col], errors="coerce")
        elif kind == "bool":
            out[col] = out[col].astype(str).str.lower().map({"true": True, "false": False})
    return out


def import_all_csvs(engine: Optional[Engine] = None) -> Dict:
    engine = engine or create_engine(DATABASE_URL)
    started_at = datetime.now(timezone.utc)
    tables_loaded: Dict[str, int] = {}
    manifest = build_manifest()

    with engine.begin() as conn:  # single transaction; rollback on any exception
        for table in reversed(LOAD_ORDER):
            conn.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))

        for table in LOAD_ORDER:
            df = pd.read_csv(CSV_FILES[table], dtype=str, keep_default_na=False)
            coerced = _coerce_dataframe(table, df)
            coerced.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=500)
            tables_loaded[table] = len(coerced)

        for name, meta in manifest["files"].items():
            if "error" in meta:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO data_provenance
                        (source_file, sha256_hash, row_count, column_count, captured_at)
                    VALUES (:source_file, :sha256_hash, :row_count, :column_count, :captured_at)
                    """
                ),
                {
                    "source_file": meta["path"],
                    "sha256_hash": meta["sha256"],
                    "row_count": meta["row_count"],
                    "column_count": meta["column_count"],
                    "captured_at": manifest["captured_at"],
                },
            )

        finished_at = datetime.now(timezone.utc)
        conn.execute(
            text(
                """
                INSERT INTO ingestion_runs
                    (run_started_at, run_finished_at, status, tables_loaded, error_message)
                VALUES (:started, :finished, :status, :tables_loaded, NULL)
                """
            ),
            {
                "started": started_at,
                "finished": finished_at,
                "status": "success",
                "tables_loaded": json.dumps(tables_loaded),
            },
        )
        # `with engine.begin()` commits automatically here; any exception above
        # rolls back the whole transaction instead.

    write_manifest(manifest)
    return {
        "tables_loaded": tables_loaded,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }


if __name__ == "__main__":
    result = import_all_csvs()
    print(json.dumps(result, indent=2))
