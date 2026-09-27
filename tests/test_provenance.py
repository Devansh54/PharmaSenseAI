from phase1.provenance import build_manifest, sha256_of_file
from phase1.config import CSV_FILES


def test_manifest_has_entry_per_csv():
    manifest = build_manifest()
    assert set(manifest["files"].keys()) == set(CSV_FILES.keys())
    for meta in manifest["files"].values():
        assert "sha256" in meta
        assert meta["row_count"] > 0


def test_hash_is_deterministic():
    path = CSV_FILES["compounds"]
    assert sha256_of_file(path) == sha256_of_file(path)
