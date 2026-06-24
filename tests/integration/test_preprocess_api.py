import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import settings
from app.main import app


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
    response = client.post("/preprocess/scan", json={"dir_name": "nonexistent"})
    assert response.status_code == 404


def test_scan_directory(client, temp_dirs):
    """Test scanning a directory."""
    pdf_input, _ = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    response = client.post("/preprocess/scan", json={"dir_name": "my_papers"})
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
        json={"dir_name": "nonexistent", "filename": "missing.pdf"},
    )
    assert response.status_code == 404


def test_convert_pdf_success(client, temp_dirs):
    """Test successful PDF conversion."""
    pdf_input, preprocessed = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    # Mock the converter backend
    mock_converter = MagicMock()
    mock_converter.convert_to_markdown.return_value = "# Converted markdown"
    mock_converter.extract_metadata.return_value = {
        "title": "Test Paper",
        "authors": ["Author"],
        "abstract": "Abstract text",
        "publication_date": "2024",
    }
    del mock_converter.convert_and_extract

    with patch(
        "app.services.preprocessing_service.get_converter", return_value=mock_converter
    ):
        response = client.post(
            "/preprocess/convert",
            json={
                "dir_name": "my_papers",
                "filename": "paper1.pdf",
                "metadata_backend": "none",
            },
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


def test_convert_batch_streams_events(client, tmp_path):
    """POST /preprocess/convert-batch converts unconverted PDFs and streams SSE."""
    from unittest.mock import MagicMock, patch

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    pdf_dir = tmp_path / "pdf_input" / "mydir"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "a.pdf").write_bytes(b"%PDF a")
    (pdf_dir / "b.pdf").write_bytes(b"%PDF b")

    # b.pdf already converted — should be skipped
    prep_dir = tmp_path / "preprocessed" / "mydir"
    prep_dir.mkdir(parents=True)
    (prep_dir / "b.md").write_text("existing")

    mock_svc = MagicMock()
    mock_svc.scan_directory.return_value = [
        {"filename": "a.pdf", "processed": False},
        {"filename": "b.pdf", "processed": True},
    ]
    mock_svc.convert_single_pdf.return_value = {"filename": "a.pdf"}

    with patch("app.api.preprocess.get_preprocessing_service", return_value=mock_svc):
        resp = client.post(
            "/preprocess/convert-batch",
            json={"dir_name": "mydir", "backend": "pymupdf",
                  "metadata_backend": "openalex", "document_type": "default"},
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    statuses = [(e.get("filename"), e.get("status")) for e in events if "filename" in e]
    assert ("a.pdf", "converting") in statuses
    assert ("a.pdf", "done") in statuses
    assert ("b.pdf", "skipped") in statuses
    done_event = next(e for e in events if e.get("done") is True)
    assert done_event["converted"] == 1
    assert done_event["skipped"] == 1
    assert done_event["errors"] == 0


def test_convert_batch_handles_conversion_error(client, tmp_path):
    """Conversion errors are non-fatal — error event emitted, processing continues."""
    from unittest.mock import MagicMock, patch

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    pdf_dir = tmp_path / "pdf_input" / "mydir"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "bad.pdf").write_bytes(b"%PDF bad")

    mock_svc = MagicMock()
    mock_svc.scan_directory.return_value = [{"filename": "bad.pdf", "processed": False}]
    mock_svc.convert_single_pdf.side_effect = RuntimeError("corrupt pdf")

    with patch("app.api.preprocess.get_preprocessing_service", return_value=mock_svc):
        resp = client.post(
            "/preprocess/convert-batch",
            json={"dir_name": "mydir", "backend": "pymupdf",
                  "metadata_backend": "openalex", "document_type": "default"},
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    error_events = [e for e in events if e.get("status") == "error"]
    assert error_events
    assert "corrupt pdf" in error_events[0]["message"]
    done_event = next(e for e in events if e.get("done") is True)
    assert done_event["errors"] == 1
    assert done_event["converted"] == 0
