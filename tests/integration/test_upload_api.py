import pytest
import sys
from pathlib import Path
import tempfile
import shutil
from io import BytesIO
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.config import settings


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests"""
    temp_dir = tempfile.mkdtemp()
    # Override settings for tests
    original_data_dir = settings.data_dir
    settings.data_dir = temp_dir
    yield temp_dir
    # Restore original and cleanup
    settings.data_dir = original_data_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client"""
    with patch('app.api.collections.QdrantService') as mock:
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.delete_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_paper_service():
    """Mock paper service"""
    with patch('app.api.papers.PaperService') as mock:
        mock_instance = Mock()
        from app.models.paper import PaperMetadata

        # Create fake metadata
        fake_metadata = PaperMetadata(
            paper_id="test-paper-id",
            title="Test Paper",
            authors=["Test Author"],
            year=2024,
            unique_id="AuthorTestPaper2024"
        )

        mock_result = {
            "metadata": fake_metadata,
            "chunks_created": 5,
            "embeddings_generated": 5
        }
        mock_instance.process_paper = Mock(return_value=mock_result)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def test_collection(client, temp_data_dir, mock_qdrant, mock_paper_service):
    """Create a test collection"""
    response = client.post(
        "/collections",
        json={"name": "Test Collection"}
    )
    return response.json()["collection_id"]


@pytest.fixture
def client(temp_data_dir, mock_qdrant, mock_paper_service):
    return TestClient(app)


@pytest.fixture
def sample_pdf():
    """Create a minimal valid PDF for testing"""
    # Minimal valid PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
0000000101 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""
    return BytesIO(pdf_content)


def test_upload_pdf(client, test_collection, sample_pdf):
    """Test uploading a PDF to a collection"""
    response = client.post(
        f"/collections/{test_collection}/papers",
        files={"file": ("test.pdf", sample_pdf, "application/pdf")}
    )

    assert response.status_code == 200
    data = response.json()
    assert "paper_id" in data
    assert "title" in data
    assert data["collection_id"] == test_collection


def test_upload_pdf_invalid_file(client, test_collection):
    """Test uploading a non-PDF file"""
    fake_file = BytesIO(b"This is not a PDF")

    response = client.post(
        f"/collections/{test_collection}/papers",
        files={"file": ("test.txt", fake_file, "text/plain")}
    )

    assert response.status_code == 400


def test_upload_pdf_to_nonexistent_collection(client, sample_pdf):
    """Test uploading to a collection that doesn't exist"""
    response = client.post(
        "/collections/nonexistent/papers",
        files={"file": ("test.pdf", sample_pdf, "application/pdf")}
    )

    assert response.status_code == 404


def test_list_papers_in_collection(client, test_collection):
    """Test listing papers in a collection"""
    response = client.get(f"/collections/{test_collection}/papers")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
