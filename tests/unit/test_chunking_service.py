import pytest
from app.services.chunking_service import ChunkingService


def test_chunk_text_fixed_size():
    """Test fixed-size chunking"""
    service = ChunkingService(chunk_size=50, overlap=10)

    text = "This is a test text. " * 20  # Long text
    chunks = service.chunk_text(text)

    assert len(chunks) > 1
    for chunk in chunks[:-1]:  # All but last
        assert len(chunk) >= 40  # At least chunk_size - overlap


def test_chunk_text_with_overlap():
    """Test chunking with overlap"""
    service = ChunkingService(chunk_size=50, overlap=10)

    text = "A" * 100
    chunks = service.chunk_text(text)

    # Check overlap between consecutive chunks
    if len(chunks) > 1:
        assert chunks[0][-10:] == chunks[1][:10]


def test_chunk_short_text():
    """Test chunking text shorter than chunk_size"""
    service = ChunkingService(chunk_size=500, overlap=100)

    text = "Short text"
    chunks = service.chunk_text(text)

    assert len(chunks) == 1
    assert chunks[0] == text
