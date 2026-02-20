import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from app.services.ingestion_service import IngestionService
from app.services.chunking_service import ChunkingService
from app.core.config import settings


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory."""
    temp_dir = tempfile.mkdtemp()
    original = settings.data_dir
    settings.data_dir = temp_dir
    yield temp_dir
    settings.data_dir = original
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_preprocessed_dir():
    """Create temporary preprocessed directory with markdown files."""
    temp_dir = tempfile.mkdtemp()
    # Create a markdown file and metadata
    (Path(temp_dir) / "paper1.md").write_text("# Paper 1\n\nContent of paper 1.")
    (Path(temp_dir) / "paper1_metadata.json").write_text(json.dumps({
        "title": "Test Paper One",
        "authors": ["Alice Smith", "Bob Jones"],
        "abstract": "An abstract.",
        "publication_date": "2024",
        "source_pdf": "paper1.pdf",
    }))
    (Path(temp_dir) / "paper2.md").write_text("# Paper 2\n\nContent of paper 2.")
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_services():
    """Create mock services for ingestion."""
    chunking = ChunkingService(chunk_size=500, overlap=100)
    ollama = Mock()
    ollama.generate_embedding.return_value = [0.1] * 1024
    ollama.generate_embeddings_batch.return_value = [[0.1] * 1024]  # One embedding
    qdrant = Mock()
    qdrant.create_collection = Mock()
    qdrant.upsert_chunks = Mock()
    return chunking, ollama, qdrant


@pytest.fixture
def service(temp_data_dir, mock_services):
    chunking, ollama, qdrant = mock_services
    return IngestionService(
        chunking_service=chunking,
        ollama_service=ollama,
        qdrant_service=qdrant,
    )


def test_scan_preprocessed_not_found(service):
    """Test scanning a non-existent directory."""
    with pytest.raises(FileNotFoundError):
        service.scan_preprocessed("/nonexistent/path")


def test_scan_preprocessed(service, temp_preprocessed_dir):
    """Test scanning preprocessed directory."""
    result = service.scan_preprocessed(temp_preprocessed_dir)
    files = result["files"]
    assert len(files) == 2

    paper1 = next(f for f in files if f["stem"] == "paper1")
    assert paper1["has_metadata"] is True
    assert paper1["markdown_file"] == "paper1.md"

    paper2 = next(f for f in files if f["stem"] == "paper2")
    assert paper2["has_metadata"] is False


def test_create_collection(service, temp_data_dir):
    """Test creating a collection."""
    info = service.create_collection("test_coll", "Test Collection", "A test")

    assert info["collection_id"] == "test_coll"
    assert info["name"] == "Test Collection"

    # Check directories created
    coll_path = Path(temp_data_dir) / "test_coll"
    assert coll_path.exists()
    assert (coll_path / "pdfs").exists()
    assert (coll_path / "figures").exists()
    assert (coll_path / "metadata").exists()
    assert (coll_path / "collection_info.json").exists()


def test_create_collection_already_exists(service, temp_data_dir):
    """Test creating a collection that already exists."""
    service.create_collection("test_coll", "Test")
    with pytest.raises(ValueError):
        service.create_collection("test_coll", "Test Again")


def test_ingest_file(service, temp_data_dir, temp_preprocessed_dir, mock_services):
    """Test ingesting a single file."""
    _, ollama, qdrant = mock_services
    # Return enough embeddings for the chunks
    ollama.generate_embeddings_batch.return_value = [[0.1] * 1024] * 10

    # Create collection first
    service.create_collection("test_coll", "Test")

    md_path = str(Path(temp_preprocessed_dir) / "paper1.md")
    meta_path = str(Path(temp_preprocessed_dir) / "paper1_metadata.json")

    result = service.ingest_file("test_coll", md_path, meta_path)

    assert result["paper_id"] == "paper1"
    assert result["chunks_created"] > 0
    assert result["embeddings_generated"] > 0
    assert "unique_id" in result

    # Check metadata was copied to collection
    meta_dest = Path(temp_data_dir) / "test_coll" / "metadata" / "paper1.json"
    assert meta_dest.exists()
    stored_meta = json.loads(meta_dest.read_text())
    assert stored_meta["title"] == "Test Paper One"
    assert stored_meta["paper_id"] == "paper1"

    # Check Qdrant was called
    qdrant.upsert_chunks.assert_called_once()


def test_ingest_file_without_metadata(service, temp_data_dir, temp_preprocessed_dir, mock_services):
    """Test ingesting a file without metadata JSON."""
    _, ollama, _ = mock_services
    ollama.generate_embeddings_batch.return_value = [[0.1] * 1024] * 10

    service.create_collection("test_coll", "Test")

    md_path = str(Path(temp_preprocessed_dir) / "paper2.md")

    result = service.ingest_file("test_coll", md_path, metadata_path=None)

    assert result["paper_id"] == "paper2"
    assert result["chunks_created"] > 0


def test_ingest_file_not_found(service, temp_data_dir):
    """Test ingesting a non-existent file."""
    service.create_collection("test_coll", "Test")
    with pytest.raises(FileNotFoundError):
        service.ingest_file("test_coll", "/nonexistent/paper.md")


def test_generate_unique_id(service):
    """Test unique ID generation."""
    uid = service._generate_unique_id("Attention Is All You Need", ["Vaswani"], 2017)
    assert "Vaswani" in uid
    assert "Attention" in uid
    assert "2017" in uid


def test_generate_unique_id_empty(service):
    """Test unique ID generation with empty data."""
    uid = service._generate_unique_id("", [], None)
    assert uid == "UnknownPaper"
