"""Configuration for the Phase 3 RAG foundation."""
from __future__ import annotations

import os
from pathlib import Path

from phase1.config import DATABASE_URL  # reuse the same Postgres connection as Phase 1/2

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "phase3" / "reports"
GOLDEN_SET_PATH = REPO_ROOT / "phase3" / "golden_set.json"

# --- Chunking ---------------------------------------------------------
# Document-preserving chunking: documents at or below CHUNK_TARGET_TOKENS
# are kept intact as a single chunk. Only longer documents are split into
# overlapping windows of ~CHUNK_TARGET_TOKENS with ~CHUNK_OVERLAP_TOKENS
# of overlap between consecutive windows.
CHUNK_TARGET_TOKENS = int(os.environ.get("PHARMASENSE_CHUNK_TARGET_TOKENS", "400"))
CHUNK_OVERLAP_TOKENS = int(os.environ.get("PHARMASENSE_CHUNK_OVERLAP_TOKENS", "50"))

# --- Embeddings ---------------------------------------------------------
EMBEDDING_MODEL_NAME = os.environ.get("PHARMASENSE_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.environ.get("PHARMASENSE_EMBEDDING_DIM", "384"))

# Bumped whenever chunking, the embedding model, or the document_chunks
# schema changes in a way that makes previously stored vectors
# incompatible with new queries/writes.
INDEX_VERSION = os.environ.get("PHARMASENSE_INDEX_VERSION", "phase3-v1")

# --- Retrieval ---------------------------------------------------------
DEFAULT_TOP_K = int(os.environ.get("PHARMASENSE_RETRIEVAL_TOP_K", "5"))

__all__ = [
    "DATABASE_URL",
    "REPO_ROOT",
    "REPORTS_DIR",
    "GOLDEN_SET_PATH",
    "CHUNK_TARGET_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIM",
    "INDEX_VERSION",
    "DEFAULT_TOP_K",
]
