"""Document-preserving chunking for research_documents.full_text.

Chunks target CHUNK_TARGET_TOKENS whitespace-delimited words as a
model-agnostic, fully offline proxy for "tokens" - no tokenizer download
is required, matching the repository guide's own "roughly N tokens"
framing (Step 3). Documents at or below the target are kept intact as a
single, unmodified chunk; only longer documents are split into
overlapping windows so a chunk boundary never silently drops context.
The embedding model tokenizes each chunk's text with its own tokenizer
internally when computing embeddings (see pharmasense.retrieval.embeddings); this
module's token count is only used to size chunk boundaries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from pharmasense.config import CHUNK_OVERLAP_TOKENS, CHUNK_TARGET_TOKENS

_WORD_PATTERN = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    token_count: int


def _tokenize(text: str) -> List[str]:
    return _WORD_PATTERN.findall(text)


def count_tokens(text: str) -> int:
    """Approximate token count used for chunk sizing (whitespace words)."""
    return len(_tokenize(text))


def chunk_document(
    full_text: str,
    target_tokens: int = CHUNK_TARGET_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> List[Chunk]:
    """Split full_text into document-preserving chunks.

    Short documents (token count <= target_tokens) are returned as a
    single chunk containing the full, unmodified text - never split,
    never overlapped. Longer documents are split into target_tokens
    windows with overlap_tokens of overlap between consecutive windows
    so retrieval never loses context at a chunk boundary.

    An empty/blank document still yields exactly one (empty) chunk, so
    every source document is represented by at least one row -
    document-preserving chunking never silently drops a document.
    """
    if overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be smaller than target_tokens")

    text = full_text or ""
    if not text.strip():
        return [Chunk(index=0, text=text, token_count=0)]

    tokens = _tokenize(text)
    total = len(tokens)

    if total <= target_tokens:
        return [Chunk(index=0, text=text, token_count=total)]

    stride = target_tokens - overlap_tokens
    chunks: List[Chunk] = []
    start = 0
    index = 0
    while start < total:
        end = min(start + target_tokens, total)
        window = tokens[start:end]
        chunks.append(Chunk(index=index, text=" ".join(window), token_count=len(window)))
        if end == total:
            break
        start += stride
        index += 1
    return chunks
