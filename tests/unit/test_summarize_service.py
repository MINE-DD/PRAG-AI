"""Unit and integration tests for summarize helpers and stream endpoint."""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.api.summarize import _parse_sections, _summaries_to_text
from app.core.config import settings
from app.main import app
from app.services.prompt_service import RenderedPrompt, get_prompt_service

# ---------------------------------------------------------------------------
# _parse_sections
# ---------------------------------------------------------------------------

SIMPLE_MD = """\
# Introduction

This is the introduction paragraph. It has enough content to pass the minimum
body length filter because it is more than one hundred and fifty characters long.

## Methods

Here we describe the methods used. Again this section is intentionally long enough
to exceed the minimum body character threshold set in the parser function.

## Results

Short.
"""

MULTI_LEVEL_MD = """\
# Background

Background text that is long enough to be included by the default filter
because it exceeds the minimum body character limit of one hundred fifty chars.

### Subsection

This is an H3 — should not be treated as a section boundary.

## Conclusion

Conclusion text that is also long enough to pass the minimum body character
threshold and be included in the final list of parsed sections without trouble.
"""


def test_parse_sections_splits_h1_and_h2():
    headings = [h for h, _ in _parse_sections(SIMPLE_MD)]
    assert headings == ["Introduction", "Methods"]


def test_parse_sections_excludes_short_body_by_default():
    """Results section body is 'Short.' — under 150 chars, so excluded."""
    headings = [h for h, _ in _parse_sections(SIMPLE_MD)]
    assert "Results" not in headings


def test_parse_sections_min_body_chars_zero_includes_short():
    """min_body_chars=0 includes every section regardless of body length."""
    headings = [h for h, _ in _parse_sections(SIMPLE_MD, min_body_chars=0)]
    assert headings == ["Introduction", "Methods", "Results"]


def test_parse_sections_h3_not_a_boundary():
    """H3 headings must not create new section splits."""
    headings = [h for h, _ in _parse_sections(MULTI_LEVEL_MD)]
    assert "Subsection" not in headings
    assert "Background" in headings
    assert "Conclusion" in headings


def test_parse_sections_preamble_excluded():
    """Text before the first heading is not returned as a section."""
    text = "Preamble text here.\n\n# Introduction\n\n" + "x" * 200
    sections = _parse_sections(text)
    assert all(h != "Preamble text here." for h, _ in sections)
    assert sections[0][0] == "Introduction"


def test_parse_sections_max_sections_cap():
    lines = []
    for i in range(60):
        lines.append(f"## Section {i}\n\n" + "x" * 200)
    headings = [h for h, _ in _parse_sections("\n\n".join(lines), max_sections=10)]
    assert len(headings) == 10


def test_parse_sections_default_cap_is_50():
    lines = []
    for i in range(60):
        lines.append(f"## Section {i}\n\n" + "x" * 200)
    headings = [h for h, _ in _parse_sections("\n\n".join(lines))]
    assert len(headings) == 50


def test_parse_sections_empty_text():
    assert _parse_sections("") == []


def test_parse_sections_no_headings():
    assert _parse_sections("Just prose, no headings at all.") == []


def test_parse_sections_body_contains_heading_text():
    """Heading text is stripped from the heading, not the body."""
    text = "## Methods\n\n" + "Methods body content. " * 10
    _, body = _parse_sections(text, min_body_chars=0)[0]
    assert not body.startswith("##")


# ---------------------------------------------------------------------------
# _summaries_to_text
# ---------------------------------------------------------------------------


def test_summaries_to_text_formats_correctly():
    summaries = [
        {"heading": "Intro", "content": "Text A."},
        {"heading": "Methods", "content": "Text B."},
    ]
    result = _summaries_to_text(summaries)
    assert "**Intro**\nText A." in result
    assert "**Methods**\nText B." in result
    assert result.index("Intro") < result.index("Methods")


def test_summaries_to_text_empty():
    assert _summaries_to_text([]) == ""


def test_summaries_to_text_missing_keys():
    """Missing heading or content keys default to empty string."""
    result = _summaries_to_text([{"heading": "H"}])
    assert "**H**" in result


# ---------------------------------------------------------------------------
# Stream endpoint — filter_sections and format_instruction
# ---------------------------------------------------------------------------

MARKDOWN_WITH_SHORT_SECTION = """\
## Introduction

This introduction section is intentionally long so it passes the default minimum
body character filter of one hundred and fifty characters in the parse function.

## Short

Too short.

## Conclusion

This conclusion section is also intentionally long enough to pass the default
minimum body character filter of one hundred and fifty characters easily.
"""


@pytest.fixture
def stream_data_dir():
    temp = tempfile.mkdtemp()
    original = settings.data_dir
    settings.data_dir = temp
    yield temp
    settings.data_dir = original
    shutil.rmtree(temp)


@pytest.fixture
def stream_preprocessed_dir():
    temp = tempfile.mkdtemp()
    original = settings.preprocessed_dir
    settings.preprocessed_dir = temp
    yield temp
    settings.preprocessed_dir = original
    shutil.rmtree(temp)


@pytest.fixture
def stream_paper(stream_data_dir, stream_preprocessed_dir):
    """Create collection + paper metadata + markdown file on disk."""
    coll_id = "test-coll"
    paper_id = "paper-abc"
    preproc_dir = "papers"
    source_pdf = "paper.pdf"

    # Collection info
    coll_path = Path(stream_data_dir) / coll_id
    (coll_path / "metadata").mkdir(parents=True)
    (coll_path / "collection_info.json").write_text(
        json.dumps({"collection_id": coll_id, "name": "Test", "search_type": "dense"})
    )

    # Paper metadata
    meta = {
        "paper_id": paper_id,
        "preprocessed_dir": preproc_dir,
        "source_pdf": source_pdf,
    }
    (coll_path / "metadata" / f"{paper_id}.json").write_text(json.dumps(meta))

    # Markdown
    md_dir = Path(stream_preprocessed_dir) / preproc_dir
    md_dir.mkdir(parents=True)
    (md_dir / "paper.md").write_text(MARKDOWN_WITH_SHORT_SECTION)

    return coll_id, paper_id


@pytest.fixture(autouse=True)
def mock_prompt_service_stream():
    mock = Mock()
    mock.render.return_value = RenderedPrompt(system="sys", user="user prompt")
    app.dependency_overrides[get_prompt_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_prompt_service, None)


@pytest.fixture
def stream_client(stream_data_dir, stream_preprocessed_dir):
    with (
        patch("app.api.summarize.QdrantService") as mock_qdrant_cls,
        patch("app.api.summarize.CollectionService") as mock_coll_cls,
        patch("app.api.summarize._get_llm_service") as mock_llm,
        patch("app.api.summarize._get_llm_info", return_value={}),
        patch("app.api.summarize.MetadataService"),
    ):
        mock_coll = Mock()
        mock_coll.get_collection.return_value = {"collection_id": "test-coll"}
        mock_coll_cls.return_value = mock_coll

        mock_qdrant = Mock()
        mock_qdrant_cls.return_value = mock_qdrant

        mock_llm_inst = Mock()
        mock_llm_inst.generate.return_value = "Generated summary."
        mock_llm.return_value = mock_llm_inst

        yield TestClient(app), mock_llm_inst


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_stream_default_excludes_short_section(stream_client, stream_paper):
    client, _ = stream_client
    coll_id, paper_id = stream_paper
    resp = client.get(f"/collections/{coll_id}/papers/{paper_id}/summarize/stream")
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    toc = next(e for e in events if e["type"] == "toc")
    assert "Short" not in toc["headings"]
    assert "Introduction" in toc["headings"]
    assert "Conclusion" in toc["headings"]


def test_stream_filter_sections_includes_short_section(stream_client, stream_paper):
    """When Short is explicitly requested via filter_sections it must appear
    even though its body is under the default 150-char threshold."""
    client, _ = stream_client
    coll_id, paper_id = stream_paper
    resp = client.get(
        f"/collections/{coll_id}/papers/{paper_id}/summarize/stream",
        params={"filter_sections": "Short"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    toc = next(e for e in events if e["type"] == "toc")
    assert toc["headings"] == ["Short"]


def test_stream_filter_sections_subsets_correctly(stream_client, stream_paper):
    client, _ = stream_client
    coll_id, paper_id = stream_paper
    resp = client.get(
        f"/collections/{coll_id}/papers/{paper_id}/summarize/stream",
        params={"filter_sections": "Introduction,Conclusion"},
    )
    events = _parse_sse(resp.text)
    toc = next(e for e in events if e["type"] == "toc")
    assert set(toc["headings"]) == {"Introduction", "Conclusion"}
    assert "Short" not in toc["headings"]


def test_stream_format_prose_passes_correct_instruction(
    stream_client, stream_paper, mock_prompt_service_stream
):
    client, _ = stream_client
    coll_id, paper_id = stream_paper
    client.get(
        f"/collections/{coll_id}/papers/{paper_id}/summarize/stream",
        params={"summary_format": "prose", "max_sentences": 4},
    )
    section_calls = [
        c
        for c in mock_prompt_service_stream.render.call_args_list
        if c.args[1] == "section"
    ]
    assert section_calls, "Expected at least one section render call"
    fi = section_calls[0].kwargs["format_instruction"]
    assert "prose" in fi
    assert "4" in fi
    assert "bullet" not in fi


def test_stream_format_bullets_passes_correct_instruction(
    stream_client, stream_paper, mock_prompt_service_stream
):
    client, _ = stream_client
    coll_id, paper_id = stream_paper
    client.get(
        f"/collections/{coll_id}/papers/{paper_id}/summarize/stream",
        params={"summary_format": "bullets", "max_sentences": 3},
    )
    section_calls = [
        c
        for c in mock_prompt_service_stream.render.call_args_list
        if c.args[1] == "section"
    ]
    assert section_calls
    fi = section_calls[0].kwargs["format_instruction"]
    assert "bullet" in fi
    assert "3" in fi
    assert "prose" not in fi


def test_stream_llm_called_once_per_section(stream_client, stream_paper):
    """Default run (no filter) should call LLM for Introduction and Conclusion."""
    client, llm_mock = stream_client
    coll_id, paper_id = stream_paper
    client.get(f"/collections/{coll_id}/papers/{paper_id}/summarize/stream")
    assert llm_mock.generate.call_count == 2


# ---------------------------------------------------------------------------
# Stream endpoint — 404 paths
# ---------------------------------------------------------------------------


def _make_stream_client(stream_data_dir, stream_preprocessed_dir, collection_return):
    """Helper: build a TestClient with the stream endpoint's deps patched."""
    from app.main import app

    with (
        patch("app.api.summarize.QdrantService"),
        patch("app.api.summarize.CollectionService") as mock_coll_cls,
        patch("app.api.summarize._get_llm_service"),
        patch("app.api.summarize._get_llm_info", return_value={}),
        patch("app.api.summarize.MetadataService"),
    ):
        mock_coll = Mock()
        mock_coll.get_collection.return_value = collection_return
        mock_coll_cls.return_value = mock_coll
        yield TestClient(app)


def test_stream_collection_not_found(stream_data_dir, stream_preprocessed_dir):
    """Returns 404 when CollectionService.get_collection returns None."""
    with (
        patch("app.api.summarize.QdrantService"),
        patch("app.api.summarize.CollectionService") as mock_coll_cls,
        patch("app.api.summarize._get_llm_service"),
        patch("app.api.summarize._get_llm_info", return_value={}),
        patch("app.api.summarize.MetadataService"),
    ):
        mock_coll = Mock()
        mock_coll.get_collection.return_value = None
        mock_coll_cls.return_value = mock_coll

        client = TestClient(app)
        resp = client.get("/collections/no-coll/papers/any-paper/summarize/stream")
        assert resp.status_code == 404


def test_stream_paper_not_found(stream_data_dir, stream_preprocessed_dir):
    """Returns 404 when paper metadata file does not exist on disk."""
    with (
        patch("app.api.summarize.QdrantService"),
        patch("app.api.summarize.CollectionService") as mock_coll_cls,
        patch("app.api.summarize._get_llm_service"),
        patch("app.api.summarize._get_llm_info", return_value={}),
        patch("app.api.summarize.MetadataService"),
    ):
        mock_coll = Mock()
        mock_coll.get_collection.return_value = {"collection_id": "test-coll"}
        mock_coll_cls.return_value = mock_coll

        client = TestClient(app)
        # No metadata file exists for this paper_id in stream_data_dir
        resp = client.get(
            "/collections/test-coll/papers/nonexistent-paper/summarize/stream"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Stream endpoint — RAG fallback path
# ---------------------------------------------------------------------------


def test_stream_rag_fallback_when_no_markdown(stream_data_dir, stream_preprocessed_dir):
    """Falls back to Qdrant chunks when markdown file is missing."""
    coll_id = "test-coll"
    paper_id = "paper-rag"

    coll_path = Path(stream_data_dir) / coll_id
    (coll_path / "metadata").mkdir(parents=True)
    (coll_path / "metadata" / f"{paper_id}.json").write_text(
        json.dumps(
            {
                "paper_id": paper_id,
                "preprocessed_dir": "missing_dir",
                "source_pdf": "paper.pdf",
            }
        )
    )

    mock_chunk = Mock()
    mock_chunk.payload = {"chunk_text": "Chunk content from Qdrant."}

    with (
        patch("app.api.summarize.QdrantService") as mock_qdrant_cls,
        patch("app.api.summarize.CollectionService") as mock_coll_cls,
        patch("app.api.summarize._get_llm_service") as mock_llm,
        patch("app.api.summarize._get_llm_info", return_value={}),
        patch("app.api.summarize.MetadataService"),
    ):
        mock_coll = Mock()
        mock_coll.get_collection.return_value = {"collection_id": coll_id}
        mock_coll_cls.return_value = mock_coll

        mock_qdrant = Mock()
        mock_qdrant.get_chunks_for_paper.return_value = [mock_chunk]
        mock_qdrant_cls.return_value = mock_qdrant

        mock_llm_inst = Mock()
        mock_llm_inst.generate.return_value = "Generated from chunk."
        mock_llm.return_value = mock_llm_inst

        client = TestClient(app)
        resp = client.get(f"/collections/{coll_id}/papers/{paper_id}/summarize/stream")

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    toc = next(e for e in events if e["type"] == "toc")
    assert toc["method"] == "rag"
    assert toc["count"] >= 1


# ---------------------------------------------------------------------------
# Stream endpoint — error SSE event on LLM failure
# ---------------------------------------------------------------------------


def test_stream_error_event_on_llm_failure(stream_client, stream_paper):
    """When LLM.generate raises, an error SSE event is emitted per section."""
    client, llm_mock = stream_client
    llm_mock.generate.side_effect = RuntimeError("LLM unavailable")
    coll_id, paper_id = stream_paper

    resp = client.get(f"/collections/{coll_id}/papers/{paper_id}/summarize/stream")

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert error_events, "Expected at least one error SSE event"
    assert "LLM unavailable" in error_events[0]["message"]
