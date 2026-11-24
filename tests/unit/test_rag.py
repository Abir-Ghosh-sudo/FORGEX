from forgex.context.rag import chunk_text


def test_chunk_text_empty():
    assert chunk_text("  ") == []


def test_chunk_text_preserves_content():
    chunks = chunk_text("alpha\nbeta\ngamma", chunk_size=10, chunk_overlap=2)
    assert chunks
    assert "alpha" in chunks[0]


def test_chunk_text_validates_overlap():
    import pytest
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=10, chunk_overlap=10)
