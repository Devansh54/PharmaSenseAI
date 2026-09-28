"""Unit tests for phase3.chunking: document-preserving chunking."""
import pytest

from phase3.chunking import chunk_document, count_tokens


def test_short_document_is_returned_as_a_single_unmodified_chunk():
    text = "Follow-up assay for SNF-1107: repeated PK study in triplicate."
    chunks = chunk_document(text, target_tokens=400, overlap_tokens=50)

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].token_count == count_tokens(text)


def test_empty_document_returns_a_single_empty_chunk():
    chunks = chunk_document("", target_tokens=400, overlap_tokens=50)
    assert len(chunks) == 1
    assert chunks[0].text == ""
    assert chunks[0].token_count == 0


def test_blank_document_returns_a_single_chunk():
    chunks = chunk_document("   \n\t  ", target_tokens=400, overlap_tokens=50)
    assert len(chunks) == 1


def test_long_document_is_split_with_configured_overlap_and_no_data_loss():
    words = [f"word{i}" for i in range(1000)]
    text = " ".join(words)

    chunks = chunk_document(text, target_tokens=400, overlap_tokens=50)

    assert len(chunks) > 1
    # Every non-final chunk is exactly target_tokens long.
    for chunk in chunks[:-1]:
        assert chunk.token_count == 400

    # Consecutive chunks overlap by exactly overlap_tokens words.
    for prev_chunk, next_chunk in zip(chunks, chunks[1:]):
        prev_words = prev_chunk.text.split()
        next_words = next_chunk.text.split()
        assert prev_words[-50:] == next_words[:50]

    # No word is skipped: walking the chunks with the known stride
    # reconstructs the full original sequence.
    reconstructed = list(chunks[0].text.split())
    for chunk in chunks[1:]:
        reconstructed.extend(chunk.text.split()[50:])
    assert reconstructed == words


def test_last_chunk_reaches_the_end_of_the_document():
    words = [f"w{i}" for i in range(410)]
    text = " ".join(words)

    chunks = chunk_document(text, target_tokens=400, overlap_tokens=50)

    assert chunks[-1].text.split()[-1] == "w409"


def test_overlap_must_be_smaller_than_target():
    with pytest.raises(ValueError):
        chunk_document("some text", target_tokens=100, overlap_tokens=100)
