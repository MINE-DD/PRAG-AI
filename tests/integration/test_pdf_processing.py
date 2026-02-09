import pytest
import sys
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.pdf_processor import PDFProcessor
from app.services.chunking_service import ChunkingService
from app.services.ollama_service import OllamaService
from app.services.qdrant_service import QdrantService
from app.services.paper_service import PaperService
from app.core.config import settings


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests"""
    temp_dir = tempfile.mkdtemp()
    original_data_dir = settings.data_dir
    settings.data_dir = temp_dir
    yield temp_dir
    settings.data_dir = original_data_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant service"""
    mock = Mock(spec=QdrantService)
    mock.create_collection = Mock()
    mock.upsert_chunks = Mock()
    mock.collection_exists = Mock(return_value=True)
    return mock


@pytest.fixture
def mock_ollama():
    """Mock Ollama service"""
    mock = Mock(spec=OllamaService)
    # Return fake embeddings (1024-dimensional vector for mxbai-embed-large)
    mock.generate_embeddings_batch = Mock(return_value=[[0.1] * 1024] * 5)
    return mock


@pytest.fixture
def mock_pdf_processor():
    """Mock PDF processor for fast tests"""
    mock = Mock(spec=PDFProcessor)

    # Create a fake PaperMetadata
    from app.models.paper import PaperMetadata
    fake_metadata = PaperMetadata(
        paper_id="test-paper-123",
        title="Test Paper on Natural Language Processing",
        authors=["Test Author"],
        year=2024,
        unique_id="AuthorTestPaper2024"
    )

    # Return fake processing result
    mock.process_pdf = Mock(return_value={
        "metadata": fake_metadata,
        "text": "This is test content. " * 100,  # Generate enough text for chunking
        "tables": [],
        "figures": []
    })
    return mock


@pytest.fixture
def services(mock_pdf_processor, mock_qdrant, mock_ollama):
    """Create service instances with mocked PDF processor"""
    chunking_service = ChunkingService(chunk_size=500, overlap=100)

    return {
        'pdf_processor': mock_pdf_processor,
        'chunking_service': chunking_service,
        'ollama_service': mock_ollama,
        'qdrant_service': mock_qdrant
    }


@pytest.fixture
def sample_pdf_path():
    """Path to a real test PDF"""
    pdf_path = Path(__file__).parent.parent.parent / "data" / "pdf_input" / "TeachingNLP_short_CAMERA_READY.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Test PDF not found at {pdf_path}")
    return pdf_path


def test_process_pdf_end_to_end(temp_data_dir, services, sample_pdf_path, mock_qdrant, mock_ollama):
    """Test complete PDF processing pipeline"""
    # Create collection directory
    collection_id = "test_collection"
    collection_dir = Path(temp_data_dir) / collection_id
    collection_dir.mkdir(parents=True)
    (collection_dir / "pdfs").mkdir()
    (collection_dir / "figures").mkdir()

    # Copy PDF to collection
    paper_id = "test-paper-123"
    pdf_dest = collection_dir / "pdfs" / f"{paper_id}.pdf"
    shutil.copy(sample_pdf_path, pdf_dest)

    # Create PaperService
    paper_service = PaperService(
        pdf_processor=services['pdf_processor'],
        chunking_service=services['chunking_service'],
        ollama_service=services['ollama_service'],
        qdrant_service=services['qdrant_service']
    )

    # Process the PDF
    result = paper_service.process_paper(
        collection_id=collection_id,
        paper_id=paper_id,
        pdf_path=pdf_dest
    )

    # Verify processing results
    assert result is not None
    assert "metadata" in result
    assert "chunks_created" in result
    assert result["chunks_created"] > 0

    # Verify embeddings were generated
    mock_ollama.generate_embeddings_batch.assert_called_once()

    # Verify chunks were stored in Qdrant
    mock_qdrant.upsert_chunks.assert_called_once()
    call_args = mock_qdrant.upsert_chunks.call_args
    assert call_args[1]["collection_name"] == collection_id
    assert len(call_args[1]["chunks"]) > 0
    assert len(call_args[1]["vectors"]) > 0


@pytest.mark.slow
def test_process_pdf_with_real_pdf(temp_data_dir, sample_pdf_path):
    """Test PDF processing extracts meaningful content from real PDF (slow test)"""
    # Create real services (not mocked)
    pdf_processor = PDFProcessor()
    chunking_service = ChunkingService(chunk_size=500, overlap=100)

    # Process PDF
    paper_id = "test-paper-456"
    result = pdf_processor.process_pdf(sample_pdf_path, paper_id)

    # Verify metadata extraction
    assert result["metadata"].title is not None
    assert result["metadata"].paper_id == paper_id
    assert len(result["text"]) > 100  # Should have substantial text

    # Chunk the text
    chunks = chunking_service.chunk_text(result["text"])

    # Verify chunking
    assert len(chunks) > 0
    assert all(len(chunk) > 0 for chunk in chunks)
    assert all(len(chunk) <= 600 for chunk in chunks)  # chunk_size + some tolerance


def test_paper_service_creates_chunks_from_pdf(temp_data_dir, services, sample_pdf_path, mock_qdrant, mock_ollama):
    """Test that PaperService creates Chunk objects with proper metadata"""
    collection_id = "test_collection"
    collection_dir = Path(temp_data_dir) / collection_id
    collection_dir.mkdir(parents=True)
    (collection_dir / "pdfs").mkdir()

    paper_id = "test-paper-789"
    pdf_dest = collection_dir / "pdfs" / f"{paper_id}.pdf"
    shutil.copy(sample_pdf_path, pdf_dest)

    paper_service = PaperService(
        pdf_processor=services['pdf_processor'],
        chunking_service=services['chunking_service'],
        ollama_service=services['ollama_service'],
        qdrant_service=services['qdrant_service']
    )

    result = paper_service.process_paper(
        collection_id=collection_id,
        paper_id=paper_id,
        pdf_path=pdf_dest
    )

    # Get the chunks that were passed to qdrant
    call_args = mock_qdrant.upsert_chunks.call_args
    chunks = call_args[1]["chunks"]

    # Verify chunk structure
    assert len(chunks) > 0
    first_chunk = chunks[0]
    assert hasattr(first_chunk, 'paper_id')
    assert hasattr(first_chunk, 'chunk_text')
    assert hasattr(first_chunk, 'chunk_type')
    assert first_chunk.paper_id == paper_id
