"""Unit tests for HuggingFaceVLMConverter.

fitz (PyMuPDF) and PIL are mocked — no real PDF needed.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.huggingface_vlm_converter import HuggingFaceVLMConverter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_converter(pages=2):
    """Return a converter with a mocked VLM service and patched _render_pages."""
    mock_service = Mock()
    conv = HuggingFaceVLMConverter(vlm_service=mock_service, dpi=72)
    fake_images = [Mock() for _ in range(pages)]
    conv._render_pages = Mock(return_value=fake_images)
    return conv, mock_service, fake_images


# ---------------------------------------------------------------------------
# convert_to_markdown
# ---------------------------------------------------------------------------


def test_convert_to_markdown_joins_pages_with_separator():
    conv, mock_svc, fake_imgs = _make_converter(pages=3)
    mock_svc.extract_from_image.side_effect = ["page1", "page2", "page3"]

    result = conv.convert_to_markdown(Path("/fake/paper.pdf"))

    assert result == "page1\n\n---\n\npage2\n\n---\n\npage3"
    assert mock_svc.extract_from_image.call_count == 3


def test_convert_to_markdown_single_page():
    conv, mock_svc, _ = _make_converter(pages=1)
    mock_svc.extract_from_image.return_value = "only page"

    result = conv.convert_to_markdown(Path("/fake/paper.pdf"))

    assert result == "only page"


def test_convert_to_markdown_passes_extract_prompt():
    conv, mock_svc, fake_imgs = _make_converter(pages=1)
    mock_svc.extract_from_image.return_value = "text"

    conv.convert_to_markdown(Path("/fake/paper.pdf"))

    call_kwargs = mock_svc.extract_from_image.call_args[1]
    assert "prompt" in call_kwargs
    assert (
        "extraction" in call_kwargs["prompt"].lower()
        or "extract" in call_kwargs["prompt"].lower()
    )


# ---------------------------------------------------------------------------
# extract_metadata
# ---------------------------------------------------------------------------


def test_extract_metadata_parses_valid_json():
    conv, mock_svc, _ = _make_converter(pages=1)
    mock_svc.extract_from_image.return_value = '{"title": "My Paper", "authors": "Alice, Bob", "abstract": "An abstract.", "year": 2023}'

    meta = conv.extract_metadata(Path("/fake/paper.pdf"), "fallback")

    assert meta["title"] == "My Paper"
    assert "Alice" in meta["authors"]
    assert "Bob" in meta["authors"]
    assert meta["abstract"] == "An abstract."
    assert meta["publication_date"] == "2023"


def test_extract_metadata_strips_markdown_fences():
    conv, mock_svc, _ = _make_converter(pages=1)
    mock_svc.extract_from_image.return_value = (
        "```json\n"
        '{"title": "Wrapped", "authors": "Carol", "abstract": null, "year": null}\n'
        "```"
    )

    meta = conv.extract_metadata(Path("/fake/paper.pdf"), "fallback")

    assert meta["title"] == "Wrapped"


def test_extract_metadata_falls_back_on_invalid_json():
    conv, mock_svc, _ = _make_converter(pages=1)
    mock_svc.extract_from_image.return_value = "not json at all"

    meta = conv.extract_metadata(Path("/fake/paper.pdf"), "my_fallback")

    assert meta["title"] == "my_fallback"
    assert meta["authors"] == []
    assert meta["abstract"] is None
    assert meta["publication_date"] is None


def test_extract_metadata_no_pages_returns_fallback():
    mock_service = Mock()
    conv = HuggingFaceVLMConverter(vlm_service=mock_service)
    conv._render_pages = Mock(return_value=[])

    meta = conv.extract_metadata(Path("/fake/empty.pdf"), "empty_fallback")

    assert meta["title"] == "empty_fallback"
    mock_service.extract_from_image.assert_not_called()


def test_extract_metadata_null_year_gives_none():
    conv, mock_svc, _ = _make_converter(pages=1)
    mock_svc.extract_from_image.return_value = (
        '{"title": "T", "authors": "", "abstract": null, "year": null}'
    )

    meta = conv.extract_metadata(Path("/fake/paper.pdf"), "fallback")

    assert meta["publication_date"] is None


# ---------------------------------------------------------------------------
# _render_pages (mocking fitz and PIL)
# ---------------------------------------------------------------------------


def test_render_pages_returns_pil_images():
    mock_service = Mock()
    conv = HuggingFaceVLMConverter(vlm_service=mock_service, dpi=150)

    mock_pix = Mock()
    mock_pix.width = 100
    mock_pix.height = 100
    mock_pix.samples = b"\x00" * (100 * 100 * 3)

    mock_page = Mock()
    mock_page.get_pixmap.return_value = mock_pix

    mock_doc = MagicMock()
    mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
    mock_doc.close = Mock()

    mock_pil_image = Mock()

    with patch("fitz.open", return_value=mock_doc):
        with patch("fitz.Matrix", return_value=Mock()):
            with patch("PIL.Image.frombytes", return_value=mock_pil_image):
                pages = conv._render_pages(Path("/fake/paper.pdf"))

    assert len(pages) == 1
    assert pages[0] is mock_pil_image
    mock_doc.close.assert_called_once()
