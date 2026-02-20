import json
import pytest
import tempfile
import shutil
from pathlib import Path

from app.services.metadata_service import MetadataService
from app.models.paper import PaperMetadata


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def service(temp_data_dir):
    return MetadataService(data_dir=temp_data_dir)


def _create_metadata_json(data_dir: str, collection_id: str, paper_id: str, metadata: dict):
    """Create a metadata JSON file in a collection."""
    meta_dir = Path(data_dir) / collection_id / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    json_path = meta_dir / f"{paper_id}.json"
    json_path.write_text(json.dumps(metadata), encoding="utf-8")


def test_get_paper_metadata_from_json(service, temp_data_dir):
    """Test loading metadata from JSON file (new flow)."""
    _create_metadata_json(temp_data_dir, "test_coll", "paper1", {
        "paper_id": "paper1",
        "title": "Test Paper",
        "authors": ["Author One", "Author Two"],
        "publication_date": "2024",
        "abstract": "An abstract.",
        "unique_id": "OneTestPaper2024",
    })

    result = service.get_paper_metadata("test_coll", "paper1")
    assert result is not None
    assert isinstance(result, PaperMetadata)
    assert result.title == "Test Paper"
    assert result.authors == ["Author One", "Author Two"]
    assert result.year == 2024
    assert result.unique_id == "OneTestPaper2024"


def test_get_paper_metadata_not_found(service):
    """Test loading metadata for non-existent paper."""
    result = service.get_paper_metadata("nonexistent", "paper1")
    assert result is None


def test_list_papers_empty(service, temp_data_dir):
    """Test listing papers in empty collection."""
    result = service.list_papers("nonexistent")
    assert result == []


def test_list_papers(service, temp_data_dir):
    """Test listing papers from metadata JSONs."""
    _create_metadata_json(temp_data_dir, "test_coll", "paper1", {
        "paper_id": "paper1",
        "title": "First Paper",
        "authors": ["Author A"],
        "publication_date": "2023",
        "unique_id": "AFirstPaper2023",
    })
    _create_metadata_json(temp_data_dir, "test_coll", "paper2", {
        "paper_id": "paper2",
        "title": "Second Paper",
        "authors": ["Author B"],
        "publication_date": "2024",
        "unique_id": "BSecondPaper2024",
    })

    result = service.list_papers("test_coll")
    assert len(result) == 2
    assert result[0]["paper_id"] == "paper1"
    assert result[0]["title"] == "First Paper"
    assert result[1]["paper_id"] == "paper2"


def test_list_papers_skips_invalid_json(service, temp_data_dir):
    """Test that invalid JSON files are skipped."""
    meta_dir = Path(temp_data_dir) / "test_coll" / "metadata"
    meta_dir.mkdir(parents=True)
    (meta_dir / "bad.json").write_text("not valid json")
    _create_metadata_json(temp_data_dir, "test_coll", "good", {
        "paper_id": "good",
        "title": "Good Paper",
        "authors": [],
        "unique_id": "GoodPaper",
    })

    result = service.list_papers("test_coll")
    assert len(result) == 1
    assert result[0]["paper_id"] == "good"
