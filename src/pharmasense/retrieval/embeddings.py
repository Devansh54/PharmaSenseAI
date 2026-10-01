"""Embedding provider contract and implementations.

Mirrors the Phase 2 LLMProvider pattern: one abstract contract plus a
real, configurable adapter (BGEEmbedder, backed by BAAI/bge-small-en-
v1.5) and a dependency-free double (DeterministicFakeEmbedder) that
tests use instead of downloading model weights or requiring network
access.
"""
from __future__ import annotations

import abc
import hashlib
from typing import List, Sequence

from pharmasense.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME


class EmbeddingProvider(abc.ABC):
    """Contract every embedding backend must implement."""

    model_name: str
    dimension: int

    @abc.abstractmethod
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Return one embedding vector per input text, in order."""
        raise NotImplementedError


class BGEEmbedder(EmbeddingProvider):
    """Real embedding provider backed by BAAI/bge-small-en-v1.5 via
    sentence-transformers.

    sentence-transformers is imported lazily inside __init__ so
    importing this module - and using EmbeddingProvider /
    DeterministicFakeEmbedder in tests - never requires the heavy
    torch/transformers dependency chain to be installed or the model
    weights to be downloaded.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, deferred

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dimension = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        # bge models recommend normalized embeddings for cosine similarity.
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]


class DeterministicFakeEmbedder(EmbeddingProvider):
    """Deterministic, dependency-free embedder for tests and CI wiring.

    Produces a fixed-dimension vector derived from a SHA-256 hash of
    the input text, so identical text always yields an identical
    vector - useful for exercising duplicate-detection, reference, and
    retrieval-plumbing tests without any model download or inference
    cost. It has no notion of semantic similarity between different
    strings, so it must never be used to claim a real retrieval-
    quality result; only BGEEmbedder does that.
    """

    def __init__(self, model_name: str = "fake-deterministic", dimension: int = EMBEDDING_DIM) -> None:
        self.model_name = model_name
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> List[float]:
        digest = hashlib.sha256((text or "").encode("utf-8")).digest()
        values: List[float] = []
        i = 0
        while len(values) < self.dimension:
            values.append(digest[i % len(digest)] / 255.0)
            i += 1
        return values
