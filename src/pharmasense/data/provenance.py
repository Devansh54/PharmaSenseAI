"""Source file hashing and dataset provenance capture (read-only)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd

from pharmasense.config import CSV_FILES, PROVENANCE_DIR


def sha256_of_file(path: Path, chunk_size: int = 65536) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest() -> Dict:
    manifest = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }
    for name, path in CSV_FILES.items():
        if not path.exists():
            manifest["files"][name] = {"error": f"missing file: {path}"}
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        manifest["files"][name] = {
            "path": str(path.relative_to(path.parents[1])),
            "sha256": sha256_of_file(path),
            "size_bytes": path.stat().st_size,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
        }
    return manifest


def write_manifest(manifest: Dict, out_dir: Path = PROVENANCE_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"manifest_{timestamp}.json"
    with open(out_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    latest_path = out_dir / "manifest_latest.json"
    with open(latest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    return out_path


def load_latest_manifest(out_dir: Path = PROVENANCE_DIR) -> Dict:
    latest_path = out_dir / "manifest_latest.json"
    if not latest_path.exists():
        return {}
    with open(latest_path) as fh:
        return json.load(fh)


if __name__ == "__main__":
    m = build_manifest()
    p = write_manifest(m)
    print(f"Wrote provenance manifest to {p}")
