import pytest
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.models.paper import PaperMetadata, Chunk, ChunkType
from app.models.collection import Collection
from app.models.rag import RAGRequest, RAGResponse, Source


def test_paper_metadata_creation():
    """Test PaperMetadata model with all fields"""
    metadata = PaperMetadata(
        paper_id="test-123",
        title="Test Paper",
        authors=["Author One", "Author Two"],
        year=2024,
        abstract="This is a test abstract",
        unique_id="AuthorTest2024"
    )

    assert metadata.paper_id == "test-123"
    assert metadata.title == "Test Paper"
    assert len(metadata.authors) == 2
    assert metadata.unique_id == "AuthorTest2024"


def test_chunk_creation():
    """Test Chunk model with required fields"""
    chunk = Chunk(
        paper_id="test-123",
        unique_id="AuthorTest2024",
        chunk_text="This is test content",
        chunk_type=ChunkType.BODY,
        page_number=1
    )

    assert chunk.paper_id == "test-123"
    assert chunk.chunk_type == ChunkType.BODY
    assert chunk.page_number == 1


def test_chunk_type_enum():
    """Test ChunkType enum values"""
    assert ChunkType.ABSTRACT == "abstract"
    assert ChunkType.BODY == "body"
    assert ChunkType.TABLE == "table"
    assert ChunkType.FIGURE_CAPTION == "figure_caption"


def test_collection_creation():
    """Test Collection model"""
    collection = Collection(
        collection_id="test-collection",
        name="Test Collection",
        description="Test description"
    )

    assert collection.collection_id == "test-collection"
    assert collection.name == "Test Collection"
    assert collection.paper_count == 0


def test_rag_request():
    """Test RAGRequest model"""
    req = RAGRequest(
        query_text="What is attention?",
        paper_ids=["paper-1", "paper-2"],
        limit=5
    )

    assert req.query_text == "What is attention?"
    assert len(req.paper_ids) == 2
    assert req.limit == 5
    assert req.chat_history == []
    assert req.use_hybrid is False


def test_rag_response_with_sources():
    """Test RAGResponse with sources"""
    source = Source(
        unique_id="AuthorTest2024",
        title="Test Paper",
        authors=["Author"],
        year=2024,
        excerpts=["Excerpt 1"],
        pages=[1]
    )

    response = RAGResponse(
        answer="This is the answer",
        sources=[source],
        cited_paper_ids=["paper-1"]
    )

    assert "answer" in response.answer
    assert len(response.sources) == 1
    assert response.sources[0].unique_id == "AuthorTest2024"
