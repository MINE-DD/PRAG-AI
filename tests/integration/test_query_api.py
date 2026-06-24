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
        patch("app.api.rag.QdrantService") as mock_rag,
    ):
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.delete_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)

        # Mock search results
        mock_search_result = Mock()
        mock_search_result.id = "chunk-123"
        mock_search_result.score = 0.95
        mock_search_result.payload = {
            "paper_id": "paper-123",
            "unique_id": "AuthorTest2024",
            "chunk_text": "This is a relevant chunk about natural language processing.",
            "chunk_type": "body",
            "page_number": 1,
            "metadata": {"chunk_index": 0},
        }
        mock_instance.search = Mock(return_value=[mock_search_result])

        mock_collections.return_value = mock_instance
        mock_rag.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_ollama():
    """Mock Ollama service"""
    with patch("app.api.rag.OllamaService") as mock:
        mock_instance = Mock()
        # Return fake embedding (1024-dimensional)
        mock_instance.generate_embedding = Mock(return_value=[0.1] * 1024)
        mock_instance.generate = Mock(
            return_value=("This is a generated answer about NLP.", {})
        )
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_metadata_service():
    """Mock metadata service"""
    with patch("app.api.rag.MetadataService") as mock:
        from app.models.paper import PaperMetadata

        mock_instance = Mock()
        # Return fake paper metadata
        fake_metadata = PaperMetadata(
            paper_id="paper-123",
            title="Test Paper on NLP",
            authors=["Smith, J.", "Doe, A."],
            year=2024,
            unique_id="SmithTestPaper2024",
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
        user="Answer the question using the context.",
    )
    app.dependency_overrides[get_prompt_service] = lambda: mock
    yield
    app.dependency_overrides.pop(get_prompt_service, None)


@pytest.fixture
def client(temp_data_dir, mock_qdrant, mock_ollama, mock_metadata_service):
    return TestClient(app)


def test_rag_query_collection(client, test_collection):
    """Test RAG querying a collection with semantic search"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "What is natural language processing?", "limit": 5},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0

    # Verify result structure
    result = data["results"][0]
    assert "chunk_text" in result
    assert "paper_id" in result
    assert "unique_id" in result
    assert "score" in result
    assert result["score"] > 0


def test_rag_query_with_paper_filter(client, test_collection):
    """Test RAG querying with paper_ids filter"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "machine learning", "paper_ids": ["paper-123"], "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) > 0


def test_rag_query_nonexistent_collection(client):
    """Test RAG querying a collection that doesn't exist"""
    response = client.post("/collections/nonexistent/rag", json={"query_text": "test"})

    assert response.status_code == 404


def test_rag_query_empty_text(client, test_collection):
    """Test RAG querying with empty query text"""
    response = client.post(
        f"/collections/{test_collection}/rag", json={"query_text": ""}
    )

    assert response.status_code == 400


def test_rag_accepts_prompt_name_field(client, test_collection):
    """prompt_name field is accepted and uses the named prompt."""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={
            "query_text": "What is attention?",
            "prompt_name": "default",
        },
    )
    assert response.status_code == 200


def test_rag_query_returns_metadata(client, test_collection):
    """Test that RAG query results include chunk metadata"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "natural language processing"},
    )

    assert response.status_code == 200
    data = response.json()
    result = data["results"][0]

    # Verify metadata fields
    assert "chunk_type" in result
    assert "page_number" in result
    assert result["chunk_type"] in ["abstract", "body", "table", "figure_caption"]


def test_rag_query_with_citations(client, test_collection):
    """Test that RAG query results include citation information"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "machine learning", "include_citations": True},
    )

    assert response.status_code == 200
    data = response.json()

    # Should have citations field
    assert "citations" in data
    assert isinstance(data["citations"], dict)

    # Citations are keyed by unique_id (citation key)
    if len(data["results"]) > 0:
        unique_id = data["results"][0]["unique_id"]
        assert unique_id in data["citations"]

        citation_info = data["citations"][unique_id]
        assert "apa" in citation_info
        assert "bibtex" in citation_info
        assert "unique_id" in citation_info


def test_rag_citations_include_pdf_url_when_metadata_present(
    client, test_collection, temp_data_dir
):
    """pdf_url in citations is built from the collection metadata JSON when it exists."""
    import json as _json

    meta_dir = Path(temp_data_dir) / test_collection / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "paper-123.json").write_text(
        _json.dumps({"preprocessed_dir": "papers", "source_pdf": "paper-123.pdf"})
    )
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "natural language processing"},
    )
    assert response.status_code == 200
    data = response.json()
    # pdf_url lives inside citations, keyed by unique_id
    assert data["citations"], "Expected at least one citation entry"
    citation = next(iter(data["citations"].values()))
    assert "pdf_url" in citation
    assert "papers" in citation["pdf_url"]
    assert "paper-123.pdf" in citation["pdf_url"]


def test_rag_citations_pdf_url_empty_without_metadata(client, test_collection):
    """pdf_url is an empty string in citations when no metadata JSON is found."""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "natural language processing"},
    )
    assert response.status_code == 200
    data = response.json()
    if data["citations"]:
        citation = next(iter(data["citations"].values()))
        assert citation.get("pdf_url", "") == ""


def test_rag_small_model_regex_matches_expected_names():
    """_SMALL_MODEL_RE matches edge model naming conventions."""
    from app.api.rag import _SMALL_MODEL_RE

    should_match = ["gemma4:e2b", "gemma3:1b", "phi3:mini", "llama3.2:3b", "qwen:tiny"]
    should_not_match = ["gemma4:27b", "llama3.1:70b", "mistral:7b", "gemini-2.5-flash"]

    for name in should_match:
        assert _SMALL_MODEL_RE.search(name), f"Expected match for {name!r}"
    for name in should_not_match:
        assert not _SMALL_MODEL_RE.search(name), f"Expected no match for {name!r}"


# ---------------------------------------------------------------------------
# Thinking mode
# ---------------------------------------------------------------------------


def test_rag_response_always_includes_thinking_field(client, test_collection):
    """Response always has a 'thinking' key (None when model doesn't think)."""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "test"},
    )
    assert response.status_code == 200
    assert "thinking" in response.json()


def test_rag_thinking_content_from_generate_surfaced_in_response(
    client, test_collection, mock_ollama
):
    """thinking content returned by generate() appears as top-level 'thinking' in response."""
    mock_ollama.generate.return_value = (
        "Final answer.",
        {"thinking": "I reasoned step by step."},
    )
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "test"},
    )
    assert response.status_code == 200
    assert response.json()["thinking"] == "I reasoned step by step."


def test_rag_think_true_forwarded_to_generate(client, test_collection, mock_ollama):
    """think=True in the request is passed through to llm_service.generate()."""
    client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "test", "think": True},
    )
    call_kwargs = mock_ollama.generate.call_args[1]
    assert call_kwargs.get("think") is True


def test_rag_think_false_forwarded_to_generate(client, test_collection, mock_ollama):
    """think=False (default) is forwarded so the model skips thinking mode."""
    client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "test", "think": False},
    )
    call_kwargs = mock_ollama.generate.call_args[1]
    assert call_kwargs.get("think") is False


def test_rag_think_true_adds_buffer_to_num_predict(client, test_collection, mock_ollama):
    """think=True adds think_tokens_buffer to max_tokens sent to generate()."""
    with patch("app.api.rag.load_config") as mock_cfg:
        mock_cfg.return_value = {
            "models": {
                "llm": {
                    "type": "local",
                    "model": "gemma4:e2b",
                    "think_tokens_buffer": 1000,
                },
                "embedding": "nomic-embed-text",
            },
            "retrieval": {"top_k": 5},
        }
        client.post(
            f"/collections/{test_collection}/rag",
            json={"query_text": "test", "max_generated_tokens": 200, "think": True},
        )
    call_kwargs = mock_ollama.generate.call_args[1]
    assert call_kwargs["max_tokens"] == 1200  # 200 answer + 1000 buffer


def test_rag_think_false_no_buffer_added(client, test_collection, mock_ollama):
    """think=False leaves max_tokens equal to max_generated_tokens (no buffer)."""
    with patch("app.api.rag.load_config") as mock_cfg:
        mock_cfg.return_value = {
            "models": {
                "llm": {
                    "type": "local",
                    "model": "gemma4:e2b",
                    "think_tokens_buffer": 1000,
                },
                "embedding": "nomic-embed-text",
            },
            "retrieval": {"top_k": 5},
        }
        client.post(
            f"/collections/{test_collection}/rag",
            json={"query_text": "test", "max_generated_tokens": 200, "think": False},
        )
    call_kwargs = mock_ollama.generate.call_args[1]
    assert call_kwargs["max_tokens"] == 200


def test_rag_small_model_prompt_fallback_when_not_found(client, test_collection):
    """When small_llm prompt is missing, endpoint still succeeds with default prompt."""
    from unittest.mock import patch

    from app.services.prompt_service import RenderedPrompt

    mock_ps = Mock()
    mock_ps.get_raw.side_effect = FileNotFoundError("small_llm not found")
    mock_ps.render.return_value = RenderedPrompt(system="sys", user="usr")

    with patch("app.api.rag.load_config") as mock_cfg:
        mock_cfg.return_value = {
            "models": {
                "llm": {
                    "type": "local",
                    "model": "gemma4:e2b",
                    "max_allowed_tokens": 512,
                },
                "embedding": "nomic-embed-text",
            },
            "retrieval": {"top_k": 5},
        }
        with patch("app.api.rag.get_prompt_service", return_value=mock_ps):
            response = client.post(
                f"/collections/{test_collection}/rag",
                json={"query_text": "test query", "prompt_name": "default"},
            )
    assert response.status_code == 200
    assert "rendered_prompt" in response.json()
