# tests/integration/test_pipeline_api.py
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_prep(files):
    """files: list of (filename, processed) tuples"""
    mock = MagicMock()
    mock.scan_directory.return_value = [
        {"filename": fn, "processed": proc} for fn, proc in files
    ]
    mock.convert_single_pdf.return_value = {"filename": "x"}
    return mock


def _make_coll(collection_id="my-dir"):
    mock = MagicMock()
    coll = MagicMock()
    coll.collection_id = collection_id
    mock.create_collection.return_value = coll
    return mock


def _make_ingest():
    mock = MagicMock()
    svc = MagicMock()
    svc.ingest_file.return_value = {"chunks": 5}
    mock.return_value = svc
    return mock


def _parse_sse(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_happy_path_two_files(client):
    """Both files unconverted → convert both, create collection, ingest both → done:true."""
    prep = _make_prep([("a.pdf", False), ("b.pdf", False)])
    coll = _make_coll("my-dir")
    ingest_factory = _make_ingest()

    # Patch Path.exists to return True so the ingest step doesn't skip files
    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    assert events[0]["step"] == "scan"
    assert events[0]["to_convert"] == 2
    convert_events = [e for e in events if e.get("step") == "convert"]
    assert len([e for e in convert_events if e["status"] == "converting"]) == 2
    assert any(e.get("done") for e in events)
    done = next(e for e in events if e.get("done"))
    assert done["collection_id"] == "my-dir"
    assert done["converted"] == 2
    assert done["skipped"] == 0
    assert done["ingested"] == 2


def test_skips_already_converted(client):
    """1 converted + 1 not → only 1 convert call, both ingested."""
    prep = _make_prep([("a.pdf", True), ("b.pdf", False)])
    coll = _make_coll("my-dir")
    ingest_factory = _make_ingest()

    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    prep.convert_single_pdf.assert_called_once()  # only 1 convert call
    done = next(e for e in events if e.get("done"))
    assert done["skipped"] == 1
    assert done["converted"] == 1


def test_collection_already_exists(client):
    """Collection already exists → emit exists status, continue to ingest."""
    prep = _make_prep([("a.pdf", True)])
    coll = _make_coll("my-dir")
    coll.create_collection.side_effect = ValueError("already exists")
    # Configure get_collection to return an existing collection with the right ID
    existing_coll = MagicMock()
    existing_coll.collection_id = "my-dir"
    coll.get_collection.return_value = existing_coll
    ingest_factory = _make_ingest()

    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    coll_event = next(e for e in events if e.get("step") == "collection")
    assert coll_event["status"] == "exists"
    assert coll_event["collection_id"] == "my-dir"
    assert "fallback" not in coll_event  # authoritative ID was used
    assert any(e.get("done") for e in events)


def test_convert_error_continues(client):
    """One convert fails → pipeline continues, errors counted."""
    prep = _make_prep([("a.pdf", False), ("b.pdf", False)])
    prep.convert_single_pdf.side_effect = [Exception("conversion failed"), None]
    coll = _make_coll("my-dir")
    ingest_factory = _make_ingest()

    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    error_events = [e for e in events if e.get("step") == "convert" and e.get("status") == "error"]
    assert len(error_events) == 1
    done = next(e for e in events if e.get("done"))
    assert done["errors"] >= 1
    assert done["ingested"] >= 1  # b.pdf was successfully converted and ingested


def test_path_traversal_rejected(client):
    """dir_name with path traversal returns 400."""
    resp = client.post("/pipeline/run", json={
        "dir_name": "../etc",
        "collection_name": "hack",
    })
    assert resp.status_code == 400
