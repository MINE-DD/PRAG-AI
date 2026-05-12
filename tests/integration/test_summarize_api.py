import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import settings
from app.main import app
from app.services.prompt_service import RenderedPrompt, get_prompt_service


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
    with (
        patch("app.api.collections.QdrantService") as mock_collections,
        patch("app.api.summarize.QdrantService") as mock_summarize,
    ):
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)
        mock_instance.get_vector_size = Mock(return_value=1024)

        # Mock search results for paper chunks
        mock_chunk = Mock()
        mock_chunk.payload = {
            "paper_id": "paper-123",
            "unique_id": "AuthorTest2024",
            "chunk_text": "This paper introduces a novel approach to natural language processing using transformers.",
            "chunk_type": "abstract",
            "page_number": 1,
            "metadata": {},
        }
        mock_instance.search = Mock(return_value=[mock_chunk] * 5)

        mock_collections.return_value = mock_instance
        mock_summarize.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_ollama():
    """Mock LLM service (was OllamaService, now provider-agnostic via _get_llm_service)"""
    with patch("app.api.summarize._get_llm_service") as mock:
        mock_instance = Mock()
        mock_instance.generate = Mock(
            return_value="This paper presents a comprehensive study on transformers in NLP. Key findings include improved performance and efficiency."
        )
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_metadata_service():
    """Mock metadata service"""
    with patch("app.api.summarize.MetadataService") as mock:
        from app.models.paper import PaperMetadata

        mock_instance = Mock()
        fake_metadata = PaperMetadata(
            paper_id="paper-123",
            title="Transformers in NLP",
            authors=["Smith, J."],
            year=2024,
            unique_id="AuthorTest2024",
        )
        mock_instance.get_paper_metadata = Mock(return_value=fake_metadata)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def test_collection(client, temp_data_dir, mock_qdrant):
    """Create a test collection"""
    response = client.post("/collections", json={"name": "Test Collection"})
    return response.json()["collection_id"]


@pytest.fixture(autouse=True)
def mock_prompt_service():
    mock = Mock()
    mock.render.return_value = RenderedPrompt(
        system="You are a research assistant.",
        user="Summarize the following papers.",
    )
    app.dependency_overrides[get_prompt_service] = lambda: mock
    yield
    app.dependency_overrides.pop(get_prompt_service, None)


@pytest.fixture
def client(temp_data_dir, mock_qdrant, mock_ollama, mock_metadata_service):
    return TestClient(app)


def test_summarize_single_paper(client, test_collection):
    """Test summarizing a single paper"""
    response = client.post(
        f"/collections/{test_collection}/summarize", json={"paper_ids": ["paper-123"]}
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "summary" in data
    assert "paper_ids" in data
    assert data["paper_ids"] == ["paper-123"]
    assert len(data["summary"]) > 0


def test_summarize_multiple_papers(client, test_collection):
    """Test summarizing multiple papers"""
    response = client.post(
        f"/collections/{test_collection}/summarize",
        json={"paper_ids": ["paper-123", "paper-456"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert len(data["paper_ids"]) == 2


def test_summarize_nonexistent_collection(client):
    """Test summarizing in nonexistent collection"""
    response = client.post(
        "/collections/nonexistent/summarize", json={"paper_ids": ["paper-123"]}
    )

    assert response.status_code == 404


def test_summarize_empty_paper_ids(client, test_collection):
    """Test summarize with empty paper_ids"""
    response = client.post(
        f"/collections/{test_collection}/summarize", json={"paper_ids": []}
    )

    # Pydantic validation returns 422 for invalid input
    assert response.status_code == 422


def test_summarize_includes_metadata(client, test_collection):
    """Test that summary includes paper metadata"""
    response = client.post(
        f"/collections/{test_collection}/summarize", json={"paper_ids": ["paper-123"]}
    )

    assert response.status_code == 200
    data = response.json()

    # Should include paper metadata
    assert "papers" in data
    assert len(data["papers"]) > 0

    paper = data["papers"][0]
    assert "paper_id" in paper
    assert "title" in paper
    assert "authors" in paper


def test_summarize_accepts_prompt_name_field(client, test_collection):
    """prompt_name field is accepted and uses the named prompt."""
    response = client.post(
        f"/collections/{test_collection}/summarize",
        json={"paper_ids": ["paper-123"], "prompt_name": "default"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# New POST endpoints: structured-abstract, explicit-claims, assess-claims
# ---------------------------------------------------------------------------

SAMPLE_SUMMARIES = [
    {"heading": "Introduction", "content": "This paper studies X."},
    {"heading": "Methods", "content": "We used method Y."},
    {"heading": "Results", "content": "We found Z."},
]


def test_structured_abstract_returns_content(client, test_collection):
    """structured-abstract endpoint returns a content string."""
    response = client.post(
        f"/collections/{test_collection}/papers/paper-123/structured-abstract",
        json={"summaries": SAMPLE_SUMMARIES},
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0


def test_explicit_claims_returns_content(client, test_collection):
    """explicit-claims endpoint returns a content string."""
    response = client.post(
        f"/collections/{test_collection}/papers/paper-123/explicit-claims",
        json={"summaries": SAMPLE_SUMMARIES},
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0


def test_assess_claims_returns_content(client, test_collection):
    """assess-claims endpoint returns a content string."""
    response = client.post(
        f"/collections/{test_collection}/papers/paper-123/assess-claims",
        json={"summaries": SAMPLE_SUMMARIES},
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0


def test_structured_abstract_empty_summaries(client, test_collection):
    """Empty summaries list is accepted (LLM still runs)."""
    response = client.post(
        f"/collections/{test_collection}/papers/paper-123/structured-abstract",
        json={"summaries": []},
    )
    assert response.status_code == 200


def test_derived_endpoints_call_llm_once_each(client, test_collection, mock_ollama):
    """Each derived endpoint makes exactly one LLM call."""
    mock_ollama.generate.reset_mock()
    client.post(
        f"/collections/{test_collection}/papers/paper-123/structured-abstract",
        json={"summaries": SAMPLE_SUMMARIES},
    )
    assert mock_ollama.generate.call_count == 1

    mock_ollama.generate.reset_mock()
    client.post(
        f"/collections/{test_collection}/papers/paper-123/explicit-claims",
        json={"summaries": SAMPLE_SUMMARIES},
    )
    assert mock_ollama.generate.call_count == 1

    mock_ollama.generate.reset_mock()
    client.post(
        f"/collections/{test_collection}/papers/paper-123/assess-claims",
        json={"summaries": SAMPLE_SUMMARIES},
    )
    assert mock_ollama.generate.call_count == 1


# ---------------------------------------------------------------------------
# POST /summarize — ValueError from prompt_service
# ---------------------------------------------------------------------------


def test_summarize_prompt_value_error_returns_422(client, test_collection):
    """ValueError raised by prompt_service.render in POST summarize → 422."""
    from app.services.prompt_service import RenderedPrompt, get_prompt_service

    err_mock = Mock()
    err_mock.render.side_effect = ValueError("unknown prompt variant")
    app.dependency_overrides[get_prompt_service] = lambda: err_mock

    try:
        response = client.post(
            f"/collections/{test_collection}/summarize",
            json={"paper_ids": ["paper-123"]},
        )
        assert response.status_code == 422
        assert "unknown prompt variant" in response.json()["detail"]
    finally:
        app.dependency_overrides[get_prompt_service] = lambda: Mock(
            render=Mock(
                return_value=RenderedPrompt(
                    system="You are a research assistant.",
                    user="Summarize the following papers.",
                )
            )
        )


# ---------------------------------------------------------------------------
# GET /collections/{coll}/papers/{paper}/summarize — single-paper endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def single_paper_dir(temp_data_dir, tmp_path):
    """Create collection + paper metadata + markdown on disk."""
    from pathlib import Path

    coll_id = "sp-coll"
    paper_id = "sp-paper"
    preproc_dir = "papers"

    coll_path = Path(temp_data_dir) / coll_id
    (coll_path / "metadata").mkdir(parents=True)
    (coll_path / "collection_info.json").write_text(
        json.dumps({"collection_id": coll_id, "name": "SP", "search_type": "dense"})
    )
    (coll_path / "metadata" / f"{paper_id}.json").write_text(
        json.dumps(
            {
                "paper_id": paper_id,
                "preprocessed_dir": preproc_dir,
                "source_pdf": "paper.pdf",
            }
        )
    )

    preproc_path = tmp_path / preproc_dir
    preproc_path.mkdir()
    (preproc_path / "paper.md").write_text("# Introduction\n\n" + "Content " * 100)

    return coll_id, paper_id, str(tmp_path)


def test_summarize_single_paper_get_markdown(client, single_paper_dir, mock_ollama):
    """GET single-paper endpoint returns method=markdown when markdown exists."""
    from app.core.config import settings

    coll_id, paper_id, preproc_root = single_paper_dir
    orig = settings.preprocessed_dir
    settings.preprocessed_dir = preproc_root
    try:
        resp = client.get(f"/collections/{coll_id}/papers/{paper_id}/summarize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "markdown"
        assert len(data["summary"]) > 0
    finally:
        settings.preprocessed_dir = orig


def test_summarize_single_paper_get_paper_not_found(client, test_collection):
    """GET single-paper endpoint returns 404 when paper metadata is missing."""
    resp = client.get(f"/collections/{test_collection}/papers/no-such-paper/summarize")
    assert resp.status_code == 404


def test_summarize_single_paper_get_collection_not_found(client):
    """GET single-paper endpoint returns 404 when collection doesn't exist."""
    resp = client.get("/collections/no-coll/papers/paper-1/summarize")
    assert resp.status_code == 404


def test_summarize_single_paper_get_rag_fallback(
    temp_data_dir, mock_qdrant, mock_ollama, mock_metadata_service
):
    """GET single-paper falls back to Qdrant when markdown is missing."""
    from pathlib import Path

    coll_id = "rag-coll"
    paper_id = "rag-paper"

    coll_path = Path(temp_data_dir) / coll_id
    (coll_path / "metadata").mkdir(parents=True)
    (coll_path / "collection_info.json").write_text(
        json.dumps({"collection_id": coll_id, "name": "RAG", "search_type": "dense"})
    )
    (coll_path / "metadata" / f"{paper_id}.json").write_text(
        json.dumps(
            {"paper_id": paper_id, "preprocessed_dir": "missing", "source_pdf": "p.pdf"}
        )
    )

    mock_chunk = Mock()
    mock_chunk.payload = {"chunk_text": "Chunk content."}
    mock_qdrant.get_chunks_for_paper = Mock(return_value=[mock_chunk])

    client = TestClient(app)
    resp = client.get(f"/collections/{coll_id}/papers/{paper_id}/summarize")
    assert resp.status_code == 200
    assert resp.json()["method"] == "rag"
