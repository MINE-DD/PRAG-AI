"""Unit tests for OllamaVLMConverter.

fitz (PyMuPDF) and ollama.Client are mocked — no real PDF or Ollama needed.
PromptService is injected via constructor and mocked in all tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.ollama_vlm_converter import OllamaVLMConverter
from app.services.prompt_service import RenderedPrompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prompt_service(system="You are an extractor.", user="Extract text."):
    mock_ps = Mock()
    mock_ps.render.return_value = RenderedPrompt(system=system, user=user)
    return mock_ps


def _make_converter(pages=2, system="sys", user="usr"):
    """Return a converter with mocked Ollama client, PromptService, and _render_pages."""
    mock_ps = _make_prompt_service(system=system, user=user)
    with patch("ollama.Client"):
        conv = OllamaVLMConverter(
            url="http://localhost:11434",
            model="llava-phi3",
            prompt_service=mock_ps,
        )
    mock_client = Mock()
    conv.client = mock_client

    fake_pages = [b"jpeg_bytes_%d" % i for i in range(pages)]
    conv._render_pages = Mock(return_value=fake_pages)

    return conv, mock_client, mock_ps, fake_pages


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_requires_prompt_service():
    with patch("ollama.Client"):
        with pytest.raises(TypeError, match="prompt_service"):
            OllamaVLMConverter()


# ---------------------------------------------------------------------------
# convert_to_markdown
# ---------------------------------------------------------------------------


def test_convert_to_markdown_joins_pages_with_separator():
    conv, mock_client, _, _ = _make_converter(pages=3)
    mock_client.chat.side_effect = [
        {"message": {"content": "page1"}},
        {"message": {"content": "page2"}},
        {"message": {"content": "page3"}},
    ]

    result = conv.convert_to_markdown(Path("/fake/paper.pdf"))

    assert result == "page1\n\n---\n\npage2\n\n---\n\npage3"
    assert mock_client.chat.call_count == 3


def test_convert_to_markdown_single_page():
    conv, mock_client, _, _ = _make_converter(pages=1)
    mock_client.chat.return_value = {"message": {"content": "only page"}}

    result = conv.convert_to_markdown(Path("/fake/paper.pdf"))

    assert result == "only page"


def test_convert_to_markdown_sends_system_and_user_messages():
    conv, mock_client, _, fake_pages = _make_converter(
        pages=1, system="be an extractor", user="extract this"
    )
    mock_client.chat.return_value = {"message": {"content": "text"}}

    conv.convert_to_markdown(Path("/fake/paper.pdf"))

    messages = mock_client.chat.call_args[1]["messages"]
    assert messages[0] == {"role": "system", "content": "be an extractor"}
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "extract this"
    assert messages[1]["images"] == [fake_pages[0]]


def test_convert_to_markdown_skips_empty_system():
    conv, mock_client, mock_ps, _ = _make_converter(pages=1)
    mock_ps.render.return_value = RenderedPrompt(system="", user="extract this")
    mock_client.chat.return_value = {"message": {"content": "text"}}

    conv.convert_to_markdown(Path("/fake/paper.pdf"))

    messages = mock_client.chat.call_args[1]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_convert_to_markdown_uses_correct_model():
    conv, mock_client, _, _ = _make_converter(pages=1)
    mock_client.chat.return_value = {"message": {"content": "text"}}

    conv.convert_to_markdown(Path("/fake/paper.pdf"))

    assert mock_client.chat.call_args[1]["model"] == "llava-phi3"


def test_convert_to_markdown_renders_extract_prompt():
    conv, mock_client, mock_ps, _ = _make_converter(pages=1)
    mock_client.chat.return_value = {"message": {"content": "text"}}

    conv.convert_to_markdown(Path("/fake/paper.pdf"))

    mock_ps.render.assert_called_once_with(
        "vlm_extract", "default", document_type="document"
    )


def test_convert_to_markdown_custom_document_type():
    mock_ps = _make_prompt_service()
    with patch("ollama.Client"):
        conv = OllamaVLMConverter(prompt_service=mock_ps, document_type="invoice")
    conv._render_pages = Mock(return_value=[b"img"])
    conv.client = Mock()
    conv.client.chat.return_value = {"message": {"content": "text"}}

    conv.convert_to_markdown(Path("/fake/invoice.pdf"))

    mock_ps.render.assert_called_once_with(
        "vlm_extract", "default", document_type="invoice"
    )


# ---------------------------------------------------------------------------
# extract_metadata
# ---------------------------------------------------------------------------


def test_extract_metadata_parses_valid_json():
    conv, mock_client, mock_ps, _ = _make_converter(pages=1)
    mock_ps.render.return_value = RenderedPrompt(system="sys", user="extract meta")
    mock_client.chat.return_value = {
        "message": {
            "content": '{"title": "My Doc", "authors": "Alice, Bob", "abstract": "Great.", "year": 2024}'
        }
    }

    meta = conv.extract_metadata(Path("/fake/paper.pdf"), "fallback")

    assert meta["title"] == "My Doc"
    assert "Alice" in meta["authors"]
    assert "Bob" in meta["authors"]
    assert meta["abstract"] == "Great."
    assert meta["publication_date"] == "2024"


def test_extract_metadata_renders_metadata_prompt():
    conv, mock_client, mock_ps, _ = _make_converter(pages=1)
    mock_ps.render.return_value = RenderedPrompt(system="", user="get meta")
    mock_client.chat.return_value = {
        "message": {
            "content": '{"title": "T", "authors": "", "abstract": null, "year": null}'
        }
    }

    conv.extract_metadata(Path("/fake/paper.pdf"), "fallback")

    mock_ps.render.assert_called_once_with(
        "vlm_metadata", "default", document_type="document"
    )


def test_extract_metadata_strips_markdown_fences():
    conv, mock_client, _, _ = _make_converter(pages=1)
    mock_client.chat.return_value = {
        "message": {
            "content": "```json\n{\"title\": \"Wrapped\", \"authors\": \"Carol\", \"abstract\": null, \"year\": null}\n```"
        }
    }

    meta = conv.extract_metadata(Path("/fake/paper.pdf"), "fallback")

    assert meta["title"] == "Wrapped"


def test_extract_metadata_falls_back_on_invalid_json():
    conv, mock_client, _, _ = _make_converter(pages=1)
    mock_client.chat.return_value = {"message": {"content": "not json"}}

    meta = conv.extract_metadata(Path("/fake/paper.pdf"), "my_fallback")

    assert meta["title"] == "my_fallback"
    assert meta["authors"] == []
    assert meta["abstract"] is None
    assert meta["publication_date"] is None


def test_extract_metadata_no_pages_returns_fallback():
    mock_ps = _make_prompt_service()
    with patch("ollama.Client"):
        conv = OllamaVLMConverter(prompt_service=mock_ps)
    mock_client = Mock()
    conv.client = mock_client
    conv._render_pages = Mock(return_value=[])

    meta = conv.extract_metadata(Path("/fake/empty.pdf"), "empty_fallback")

    assert meta["title"] == "empty_fallback"
    mock_client.chat.assert_not_called()


def test_extract_metadata_only_uses_first_page():
    conv, mock_client, _, fake_pages = _make_converter(pages=3)
    mock_client.chat.return_value = {
        "message": {
            "content": '{"title": "T", "authors": "", "abstract": null, "year": null}'
        }
    }

    conv.extract_metadata(Path("/fake/paper.pdf"), "fallback")

    assert mock_client.chat.call_count == 1
    messages = mock_client.chat.call_args[1]["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert user_msg["images"] == [fake_pages[0]]


# ---------------------------------------------------------------------------
# _render_pages (mocking fitz)
# ---------------------------------------------------------------------------


def test_render_pages_returns_jpeg_bytes():
    mock_ps = _make_prompt_service()
    with patch("ollama.Client"):
        conv = OllamaVLMConverter(prompt_service=mock_ps, dpi=150)

    fake_jpeg = b"\xff\xd8\xff"

    mock_pix = Mock()
    mock_pix.tobytes.return_value = fake_jpeg

    mock_page = Mock()
    mock_page.get_pixmap.return_value = mock_pix

    mock_doc = MagicMock()
    mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
    mock_doc.close = Mock()

    with patch("fitz.open", return_value=mock_doc):
        with patch("fitz.Matrix", return_value=Mock()):
            pages = conv._render_pages(Path("/fake/paper.pdf"))

    assert len(pages) == 1
    assert pages[0] == fake_jpeg
    mock_pix.tobytes.assert_called_once_with("jpeg")
    mock_doc.close.assert_called_once()
