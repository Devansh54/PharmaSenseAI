"""Unit tests for phase3.embeddings.DeterministicFakeEmbedder."""
from phase3.embeddings import DeterministicFakeEmbedder


def test_same_text_yields_identical_vector():
    embedder = DeterministicFakeEmbedder(dimension=16)
    a = embedder.embed(["hello world"])[0]
    b = embedder.embed(["hello world"])[0]
    assert a == b


def test_vector_matches_configured_dimension():
    embedder = DeterministicFakeEmbedder(dimension=32)
    vector = embedder.embed(["some text"])[0]
    assert len(vector) == 32
    assert embedder.dimension == 32


def test_different_text_yields_different_vectors():
    embedder = DeterministicFakeEmbedder(dimension=16)
    a, b = embedder.embed(["alpha", "beta"])
    assert a != b


def test_embed_preserves_input_order():
    embedder = DeterministicFakeEmbedder(dimension=8)
    vectors = embedder.embed(["one", "two", "three"])
    assert vectors[0] == embedder.embed(["one"])[0]
    assert vectors[2] == embedder.embed(["three"])[0]
