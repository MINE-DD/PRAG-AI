# tests/integration/test_zotero_api.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from unittest.mock import MagicMock, patch

import pytest
from app.core.config import settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")
    return TestClient(app)


def _mock_keys(has_zotero=True, user_id="12345"):
    mock = MagicMock()
    mock.has_key.side_effect = lambda p: p == "zotero" and has_zotero
    mock.get_key.side_effect = lambda p: (
        "fakekey" if p == "zotero" and has_zotero else None
    )
    return mock


def test_list_collections_returns_400_when_not_configured(client):
    with (
        patch("app.api.zotero._api_keys") as mock_keys,
        patch("app.api.zotero._get_user_id", return_value=""),
    ):
        mock_keys.has_key.return_value = False
        mock_keys.get_key.return_value = None
        resp = client.get("/zotero/collections")
    assert resp.status_code == 400
    assert "Settings" in resp.json()["detail"]


def test_list_collections_returns_list(client):
    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_collections") as mock_list,
    ):
        mock_list.return_value = [{"key": "C1", "name": "My Papers"}]
        resp = client.get("/zotero/collections")
    assert resp.status_code == 200
    assert resp.json() == [{"key": "C1", "name": "My Papers"}]


def test_list_items_returns_items(client):
    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items") as mock_items,
    ):
        mock_items.return_value = [
            {
                "item_key": "I1",
                "title": "Paper",
                "authors": [],
                "attachment": {
                    "type": "cloud",
                    "filename": "p.pdf",
                    "attachment_key": "A1",
                },
            }
        ]
        resp = client.get("/zotero/collections/C1/items")
    assert resp.status_code == 200
    assert resp.json()[0]["item_key"] == "I1"


def test_import_streams_done_event(client, tmp_path):
    """POST /zotero/import streams SSE events and ends with done:true."""
    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    items_by_key = {
        "I1": {
            "item_key": "I1",
            "title": "Test",
            "authors": ["Alice"],
            "year": 2023,
            "doi": None,
            "journal": None,
            "abstract": None,
            "attachment": {
                "type": "cloud",
                "filename": "test.pdf",
                "attachment_key": "A1",
            },
        }
    }
    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items") as mock_items,
        patch("app.services.zotero_service.download_pdf", return_value=b"%PDF fake"),
    ):
        mock_items.return_value = list(items_by_key.values())
        resp = client.post(
            "/zotero/import",
            json={
                "collection_key": "C1",
                "dir_name": "mycol",
                "item_keys": ["I1"],
            },
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(e.get("done") for e in events)
    statuses = {e.get("filename"): e.get("status") for e in events if "filename" in e}
    assert statuses.get("test.pdf") == "done"

    # PDF written to _zt dir
    pdf_path = tmp_path / "pdf_input" / "mycol_zt" / "test.pdf"
    assert pdf_path.exists()
    # Metadata written
    meta_path = tmp_path / "preprocessed" / "mycol_zt" / "test_metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["metadata_source"] == "zotero"
    assert meta["title"] == "Test"


def test_import_always_downloads(client, tmp_path):
    """Re-importing an existing PDF always re-downloads and overwrites."""
    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    # Pre-create the PDF to simulate a previous import
    pdf_dir = tmp_path / "pdf_input" / "mycol_zt"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "test.pdf").write_bytes(b"existing")

    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items") as mock_items,
        patch(
            "app.services.zotero_service.download_pdf", return_value=b"%PDF new"
        ) as mock_dl,
    ):
        mock_items.return_value = [
            {
                "item_key": "I1",
                "title": "Test",
                "authors": [],
                "year": None,
                "doi": None,
                "journal": None,
                "abstract": None,
                "attachment": {
                    "type": "cloud",
                    "filename": "test.pdf",
                    "attachment_key": "A1",
                },
            }
        ]
        resp = client.post(
            "/zotero/import",
            json={
                "collection_key": "C1",
                "dir_name": "mycol",
                "item_keys": ["I1"],
            },
        )

    mock_dl.assert_called_once()
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    statuses = {e.get("filename"): e.get("status") for e in events if "filename" in e}
    assert statuses.get("test.pdf") == "done"


# ---------------------------------------------------------------------------
# Local storage fallback helpers + tests
# ---------------------------------------------------------------------------

_ITEM = {
    "item_key": "I1",
    "title": "Paper",
    "authors": ["Alice"],
    "year": 2024,
    "doi": None,
    "journal": None,
    "abstract": None,
    "attachment": {"type": "cloud", "filename": "paper.pdf", "attachment_key": "A1"},
}

_EMPTY_CONFIG = {
    "models": {"embedding": "m", "llm": {"type": "local", "model": "m"}},
    "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
    "retrieval": {"top_k": 5},
    "zotero_local_storage": "",
}


def test_import_falls_back_to_local_storage(client, tmp_path):
    """When Zotero cloud fails, the importer reads the PDF from local Zotero storage."""
    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    local_storage = tmp_path / "zotero_storage"
    (local_storage / "A1").mkdir(parents=True)
    (local_storage / "A1" / "paper.pdf").write_bytes(b"%PDF local")

    cfg = {**_EMPTY_CONFIG, "zotero_local_storage": str(local_storage)}

    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items", return_value=[_ITEM]),
        patch(
            "app.services.zotero_service.download_pdf",
            side_effect=RuntimeError("PDF not found in Zotero cloud"),
        ),
        patch("app.api.zotero.load_config", return_value=cfg),
    ):
        resp = client.post(
            "/zotero/import",
            json={"collection_key": "C1", "dir_name": "col", "item_keys": ["I1"]},
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    statuses = {e.get("filename"): e.get("status") for e in events if "filename" in e}
    assert statuses.get("paper.pdf") == "done"
    assert (
        tmp_path / "pdf_input" / "col_zt" / "paper.pdf"
    ).read_bytes() == b"%PDF local"


def test_import_errors_when_cloud_404_and_no_local_storage(client, tmp_path):
    """Without local storage configured, a cloud 404 propagates as an error event."""
    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items", return_value=[_ITEM]),
        patch(
            "app.services.zotero_service.download_pdf",
            side_effect=RuntimeError("PDF not found in Zotero cloud"),
        ),
        patch("app.api.zotero.load_config", return_value=_EMPTY_CONFIG),
    ):
        resp = client.post(
            "/zotero/import",
            json={"collection_key": "C1", "dir_name": "col", "item_keys": ["I1"]},
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    error_events = [e for e in events if e.get("status") == "error"]
    assert error_events, "Expected an error event"
    assert "not found" in error_events[0]["message"].lower()


def test_import_with_auto_convert_emits_convert_events(client, tmp_path):
    """When auto_convert=True, convert events are emitted after each download."""
    from unittest.mock import MagicMock, patch

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    mock_svc = MagicMock()
    mock_svc.convert_single_pdf.return_value = {"filename": "test.pdf"}

    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items") as mock_items,
        patch("app.services.zotero_service.download_pdf", return_value=b"%PDF fake"),
        patch("app.api.zotero.load_config", return_value=_EMPTY_CONFIG),
        patch("app.api.zotero.PreprocessingService", return_value=mock_svc),
    ):
        mock_items.return_value = [
            {
                "item_key": "I1",
                "title": "Test",
                "authors": ["Alice"],
                "year": 2023,
                "doi": None,
                "journal": None,
                "abstract": None,
                "attachment": {
                    "type": "cloud",
                    "filename": "test.pdf",
                    "attachment_key": "A1",
                },
            }
        ]
        resp = client.post(
            "/zotero/import",
            json={
                "collection_key": "C1",
                "dir_name": "mycol",
                "item_keys": ["I1"],
                "auto_convert": True,
                "pdf_backend": "pymupdf",
                "metadata_backend": "openalex",
                "document_type": "default",
            },
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(
        e.get("filename") == "test.pdf" and e.get("status") == "converted"
        for e in events
    )
    mock_svc.convert_single_pdf.assert_called_once_with(
        "mycol_zt",
        "test.pdf",
        backend="pymupdf",
        metadata_backend="openalex",
        document_type="default",
    )


def test_import_auto_convert_error_is_nonfatal(client, tmp_path):
    """A conversion failure emits convert_error but does not stop remaining downloads."""
    from unittest.mock import MagicMock, patch

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    mock_svc = MagicMock()
    mock_svc.convert_single_pdf.side_effect = RuntimeError("bad pdf")

    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items") as mock_items,
        patch("app.services.zotero_service.download_pdf", return_value=b"%PDF fake"),
        patch("app.api.zotero.load_config", return_value=_EMPTY_CONFIG),
        patch("app.api.zotero.PreprocessingService", return_value=mock_svc),
    ):
        mock_items.return_value = [
            {
                "item_key": "I1",
                "title": "Test",
                "authors": [],
                "year": None,
                "doi": None,
                "journal": None,
                "abstract": None,
                "attachment": {
                    "type": "cloud",
                    "filename": "test.pdf",
                    "attachment_key": "A1",
                },
            }
        ]
        resp = client.post(
            "/zotero/import",
            json={
                "collection_key": "C1",
                "dir_name": "mycol",
                "item_keys": ["I1"],
                "auto_convert": True,
            },
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(e.get("status") == "convert_error" for e in events)
    assert any(e.get("done") for e in events)
