# tests/integration/test_zotero_api.py
import sys
import json
import tempfile
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


@pytest.fixture
def client(tmp_path):
    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")
    return TestClient(app)


def _mock_keys(has_zotero=True, user_id="12345"):
    mock = MagicMock()
    mock.has_key.side_effect = lambda p: p == "zotero" and has_zotero
    mock.get_key.side_effect = lambda p: "fakekey" if p == "zotero" and has_zotero else None
    return mock


def test_list_collections_returns_400_when_not_configured(client):
    with patch("app.api.zotero._api_keys") as mock_keys, \
         patch("app.api.zotero._get_user_id", return_value=""):
        mock_keys.has_key.return_value = False
        mock_keys.get_key.return_value = None
        resp = client.get("/zotero/collections")
    assert resp.status_code == 400
    assert "Settings" in resp.json()["detail"]


def test_list_collections_returns_list(client):
    with patch("app.api.zotero._api_keys", _mock_keys()), \
         patch("app.api.zotero._get_user_id", return_value="12345"), \
         patch("app.services.zotero_service.list_collections") as mock_list:
        mock_list.return_value = [{"key": "C1", "name": "My Papers"}]
        resp = client.get("/zotero/collections")
    assert resp.status_code == 200
    assert resp.json() == [{"key": "C1", "name": "My Papers"}]


def test_list_items_returns_items(client):
    with patch("app.api.zotero._api_keys", _mock_keys()), \
         patch("app.api.zotero._get_user_id", return_value="12345"), \
         patch("app.services.zotero_service.list_items") as mock_items:
        mock_items.return_value = [
            {"item_key": "I1", "title": "Paper", "authors": [],
             "attachment": {"type": "cloud", "filename": "p.pdf", "attachment_key": "A1"}}
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
            "item_key": "I1", "title": "Test", "authors": ["Alice"],
            "year": 2023, "doi": None, "journal": None, "abstract": None,
            "attachment": {"type": "cloud", "filename": "test.pdf", "attachment_key": "A1"},
        }
    }
    with patch("app.api.zotero._api_keys", _mock_keys()), \
         patch("app.api.zotero._get_user_id", return_value="12345"), \
         patch("app.services.zotero_service.list_items") as mock_items, \
         patch("app.services.zotero_service.download_pdf", return_value=b"%PDF fake"):
        mock_items.return_value = list(items_by_key.values())
        resp = client.post("/zotero/import", json={
            "collection_key": "C1",
            "dir_name": "mycol",
            "item_keys": ["I1"],
        })

    assert resp.status_code == 200
    events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
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


def test_import_skips_existing_pdf(client, tmp_path):
    """Re-importing an existing PDF streams 'skipped' status."""
    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    # Pre-create the PDF
    pdf_dir = tmp_path / "pdf_input" / "mycol_zt"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "test.pdf").write_bytes(b"existing")

    with patch("app.api.zotero._api_keys", _mock_keys()), \
         patch("app.api.zotero._get_user_id", return_value="12345"), \
         patch("app.services.zotero_service.list_items") as mock_items, \
         patch("app.services.zotero_service.download_pdf") as mock_dl:
        mock_items.return_value = [{
            "item_key": "I1", "title": "Test", "authors": [], "year": None,
            "doi": None, "journal": None, "abstract": None,
            "attachment": {"type": "cloud", "filename": "test.pdf", "attachment_key": "A1"},
        }]
        resp = client.post("/zotero/import", json={
            "collection_key": "C1", "dir_name": "mycol", "item_keys": ["I1"],
        })

    mock_dl.assert_not_called()
    events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    statuses = {e.get("filename"): e.get("status") for e in events if "filename" in e}
    assert statuses.get("test.pdf") == "skipped"
