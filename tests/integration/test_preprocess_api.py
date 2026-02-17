import pytest
import sys
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.config import settings


@pytest.fixture
def temp_dirs():
    """Create temporary directories for preprocessing tests."""
    pdf_input = tempfile.mkdtemp()
    preprocessed = tempfile.mkdtemp()
    original_pdf_input = settings.pdf_input_dir
    original_preprocessed = settings.preprocessed_dir
    settings.pdf_input_dir = pdf_input
    settings.preprocessed_dir = preprocessed
    yield pdf_input, preprocessed
    settings.pdf_input_dir = original_pdf_input
    settings.preprocessed_dir = original_preprocessed
    shutil.rmtree(pdf_input)
    shutil.rmtree(preprocessed)


@pytest.fixture
def client(temp_dirs):
    return TestClient(app)


def _create_fake_pdf(directory: str, filename: str):
    path = Path(directory) / filename
    path.write_bytes(b"%PDF-1.4 fake content")


def test_list_directories_empty(client):
    """Test listing directories when none exist."""
    response = client.get("/preprocess/directories")
    assert response.status_code == 200
    assert response.json() == []


def test_list_directories(client, temp_dirs):
    """Test listing directories with PDFs."""
    pdf_input, _ = temp_dirs
    dir1 = Path(pdf_input) / "papers_a"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    response = client.get("/preprocess/directories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "papers_a"
    assert data[0]["pdf_count"] == 1


def test_scan_directory_not_found(client):
    """Test scanning a non-existent directory."""
    response = client.post(
        "/preprocess/scan",
        json={"dir_name": "nonexistent"}
    )
    assert response.status_code == 404


def test_scan_directory(client, temp_dirs):
    """Test scanning a directory."""
    pdf_input, _ = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    response = client.post(
        "/preprocess/scan",
        json={"dir_name": "my_papers"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["dir_name"] == "my_papers"
    assert len(data["files"]) == 1
    assert data["files"][0]["filename"] == "paper1.pdf"
    assert data["files"][0]["processed"] is False


def test_convert_pdf_not_found(client):
    """Test converting a non-existent PDF."""
    response = client.post(
        "/preprocess/convert",
        json={"dir_name": "nonexistent", "filename": "missing.pdf"}
    )
    assert response.status_code == 404


@patch("app.services.preprocessing_service.DocumentConverter")
def test_convert_pdf_success(mock_converter_cls, client, temp_dirs):
    """Test successful PDF conversion."""
    pdf_input, preprocessed = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    # Mock Docling
    mock_doc = MagicMock()
    mock_doc.export_to_markdown.return_value = "# Converted markdown"
    mock_doc.title = "Test Paper"
    mock_doc.authors = ["Author"]
    mock_doc.abstract = "Abstract text"
    mock_doc.publication_date = "2024"

    mock_result = MagicMock()
    mock_result.document = mock_doc
    mock_converter_cls.return_value.convert.return_value = mock_result

    response = client.post(
        "/preprocess/convert",
        json={"dir_name": "my_papers", "filename": "paper1.pdf"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "paper1.pdf"
    assert data["markdown_length"] > 0

    # Verify files exist
    output_dir = Path(preprocessed) / "my_papers"
    assert (output_dir / "paper1.md").exists()
    assert (output_dir / "paper1_metadata.json").exists()


def test_get_history_empty(client):
    """Test getting empty history."""
    response = client.get("/preprocess/history")
    assert response.status_code == 200
    assert response.json() == {"directories": {}}
