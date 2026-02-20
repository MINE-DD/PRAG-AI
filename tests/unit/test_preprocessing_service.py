import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.preprocessing_service import PreprocessingService


@pytest.fixture
def temp_dirs():
    """Create temporary input and output directories."""
    pdf_input = tempfile.mkdtemp()
    preprocessed = tempfile.mkdtemp()
    yield pdf_input, preprocessed
    shutil.rmtree(pdf_input)
    shutil.rmtree(preprocessed)


@pytest.fixture
def service(temp_dirs):
    """Create PreprocessingService with temp dirs."""
    pdf_input, preprocessed = temp_dirs
    return PreprocessingService(
        pdf_input_dir=pdf_input,
        preprocessed_dir=preprocessed,
    )


def _create_fake_pdf(directory: str, filename: str) -> Path:
    """Create a fake PDF file for testing."""
    path = Path(directory) / filename
    path.write_bytes(b"%PDF-1.4 fake content")
    return path


def test_list_directories_empty(service):
    """Test listing directories when none exist."""
    result = service.list_directories()
    assert result == []


def test_list_directories_with_subdirs(service, temp_dirs):
    """Test listing directories with PDFs."""
    pdf_input, _ = temp_dirs
    # Create directories with PDFs
    dir1 = Path(pdf_input) / "papers_a"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")
    _create_fake_pdf(str(dir1), "paper2.pdf")

    dir2 = Path(pdf_input) / "papers_b"
    dir2.mkdir()
    _create_fake_pdf(str(dir2), "paper3.pdf")

    result = service.list_directories()
    assert len(result) == 2
    # Sorted alphabetically
    assert result[0]["name"] == "papers_a"
    assert result[0]["pdf_count"] == 2
    assert result[1]["name"] == "papers_b"
    assert result[1]["pdf_count"] == 1


def test_scan_directory_not_found(service):
    """Test scanning a non-existent directory."""
    with pytest.raises(FileNotFoundError):
        service.scan_directory("nonexistent")


def test_scan_directory_unprocessed(service, temp_dirs):
    """Test scanning a directory with no processed files."""
    pdf_input, _ = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")
    _create_fake_pdf(str(dir1), "paper2.pdf")

    result = service.scan_directory("my_papers")
    assert len(result) == 2
    assert all(not f["processed"] for f in result)


def test_scan_directory_partially_processed(service, temp_dirs):
    """Test scanning a directory with some processed files."""
    pdf_input, preprocessed = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")
    _create_fake_pdf(str(dir1), "paper2.pdf")

    # Simulate paper1 already processed
    output_dir = Path(preprocessed) / "my_papers"
    output_dir.mkdir(parents=True)
    (output_dir / "paper1.md").write_text("# Paper 1 content")

    result = service.scan_directory("my_papers")
    assert len(result) == 2
    paper1 = next(f for f in result if f["filename"] == "paper1.pdf")
    paper2 = next(f for f in result if f["filename"] == "paper2.pdf")
    assert paper1["processed"] is True
    assert paper2["processed"] is False


@patch.object(PreprocessingService, "__init__", lambda self, **kw: None)
def test_convert_single_pdf_file_not_found():
    """Test converting a non-existent PDF."""
    service = PreprocessingService()
    service.pdf_input_dir = Path("/nonexistent")
    service.preprocessed_dir = Path("/nonexistent_out")
    service.history_path = service.preprocessed_dir / "history.json"

    with pytest.raises(FileNotFoundError):
        service.convert_single_pdf("dir", "missing.pdf")


def test_convert_single_pdf_success(service, temp_dirs):
    """Test successful PDF conversion with mocked backend."""
    pdf_input, preprocessed = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    mock_converter = MagicMock()
    mock_converter.convert_to_markdown.return_value = "# Test Paper\n\nSome content here."
    mock_converter.extract_metadata.return_value = {
        "title": "Test Paper",
        "authors": [],
        "abstract": None,
        "publication_date": None,
    }
    # Remove convert_and_extract so the else branch is used
    del mock_converter.convert_and_extract

    with patch("app.services.preprocessing_service.get_converter", return_value=mock_converter):
        result = service.convert_single_pdf("my_papers", "paper1.pdf", metadata_backend="none")

    assert result["filename"] == "paper1.pdf"
    assert result["markdown_length"] > 0

    output_dir = Path(preprocessed) / "my_papers"
    assert (output_dir / "paper1.md").exists()
    assert (output_dir / "paper1_metadata.json").exists()

    metadata = json.loads((output_dir / "paper1_metadata.json").read_text())
    assert metadata["title"] == "Test Paper"
    assert metadata["source_pdf"] == "paper1.pdf"


def test_get_history_empty(service):
    """Test getting history when none exists."""
    result = service.get_history()
    assert result == {"directories": {}}


def test_history_updated_after_conversion(service, temp_dirs):
    """Test that history is updated after conversion."""
    pdf_input, preprocessed = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    mock_converter = MagicMock()
    mock_converter.convert_to_markdown.return_value = "# Content"
    mock_converter.extract_metadata.return_value = {
        "title": "Content",
        "authors": [],
        "abstract": None,
        "publication_date": None,
    }
    del mock_converter.convert_and_extract

    with patch("app.services.preprocessing_service.get_converter", return_value=mock_converter):
        service.convert_single_pdf("my_papers", "paper1.pdf", metadata_backend="none")

    history = service.get_history()
    assert "my_papers" in history["directories"]
    assert "paper1.pdf" in history["directories"]["my_papers"]["files"]
    assert history["directories"]["my_papers"]["last_processed"] is not None
