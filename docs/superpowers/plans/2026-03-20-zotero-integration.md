# Zotero Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to import PDFs from their Zotero library into PRAG as an alternative to manual upload, with metadata pre-filled from Zotero.

**Architecture:** Import downloads PDFs + pre-writes `_metadata.json` to the preprocessed dir; the user then converts (PDF→markdown) and ingests via the unchanged existing flow. The convert step gains a one-guard to skip enrichment when a `_metadata.json` already exists. All Zotero-imported dirs are suffixed `_zt` server-side.

**Tech Stack:** Python 3.12, FastAPI, httpx (sync), Vue 3 (no bundler), pytest

**Spec:** `docs/superpowers/specs/2026-03-20-zotero-integration-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/services/zotero_service.py` | Create | `list_collections`, `list_items`, `download_pdf`, `normalize_metadata` |
| `backend/app/api/zotero.py` | Create | Three HTTP endpoints + SSE import |
| `backend/app/main.py` | Modify | Register zotero router |
| `backend/app/services/preprocessing_service.py` | Modify | Skip enrichment+write when `_metadata.json` exists; merge `backend`+`preprocessed_at` in |
| `backend/app/api/settings.py` | Modify | Add `zotero_user_id`, `zotero_key`, `clear_zotero_key` to request/response/handler |
| `config.yaml` | Modify | Add `zotero.user_id: ""` section |
| `tests/unit/test_zotero_service.py` | Create | Unit tests for all four service functions |
| `tests/unit/test_preprocessing_service.py` | Modify | Tests for the new skip-enrichment guard |
| `tests/integration/test_zotero_api.py` | Create | Integration tests for the three endpoints |
| `frontend-web/js/app.js` | Modify | Zotero User ID + API Key in settings form |
| `frontend-web/js/pdf-tab.js` | Modify | Zotero import panel |

---

## Task 1: `normalize_metadata`

**Files:**
- Create: `backend/app/services/zotero_service.py`
- Create: `tests/unit/test_zotero_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_zotero_service.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.services.zotero_service import normalize_metadata


def test_normalize_metadata_full():
    item = {
        "item_key": "ABC123",
        "title": "Deep Learning Survey",
        "authors": ["LeCun, Yann", "Bengio, Yoshua"],
        "year": 2015,
        "doi": "10.1038/nature14539",
        "journal": "Nature",
        "abstract": "A review of deep learning.",
        "attachment": {
            "type": "cloud",
            "filename": "lecun2015.pdf",
            "attachment_key": "DEF456",
        },
    }
    result = normalize_metadata(item)
    assert result["title"] == "Deep Learning Survey"
    assert result["authors"] == ["LeCun, Yann", "Bengio, Yoshua"]
    assert result["publication_date"] == "2015"
    assert result["doi"] == "10.1038/nature14539"
    assert result["journal"] == "Nature"
    assert result["abstract"] == "A review of deep learning."
    assert result["metadata_source"] == "zotero"
    assert result["source_pdf"] == "lecun2015.pdf"


def test_normalize_metadata_missing_fields():
    item = {
        "item_key": "XYZ",
        "title": "Minimal Paper",
        "authors": [],
        "year": None,
        "doi": None,
        "journal": None,
        "abstract": None,
        "attachment": {"type": "cloud", "filename": "minimal.pdf", "attachment_key": "K1"},
    }
    result = normalize_metadata(item)
    assert result["title"] == "Minimal Paper"
    assert result["authors"] == []
    assert result["publication_date"] is None
    assert result["doi"] is None
    assert result["metadata_source"] == "zotero"
    assert result["source_pdf"] == "minimal.pdf"
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_zotero_service.py -v
```
Expected: `ModuleNotFoundError` or `ImportError` — `zotero_service` does not exist yet.

- [ ] **Step 3: Create `zotero_service.py` with `normalize_metadata`**

```python
# backend/app/services/zotero_service.py
"""Zotero API integration: list collections/items, download PDFs, normalize metadata."""

import time
import httpx

ZOTERO_API_BASE = "https://api.zotero.org"


def normalize_metadata(zotero_item: dict) -> dict:
    """Convert a Zotero item dict to the standard _metadata.json format.

    Matches the output shape of OpenAlex/CrossRef/Semantic Scholar providers.
    Does NOT include 'backend' or 'preprocessed_at' — those are added by the
    convert step when it processes the PDF.
    """
    year = zotero_item.get("year")
    attachment = zotero_item.get("attachment") or {}
    return {
        "title": zotero_item.get("title"),
        "authors": zotero_item.get("authors") or [],
        "publication_date": str(year) if year else None,
        "abstract": zotero_item.get("abstract"),
        "doi": zotero_item.get("doi"),
        "journal": zotero_item.get("journal"),
        "metadata_source": "zotero",
        "source_pdf": attachment.get("filename"),
    }
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_zotero_service.py -v
```
Expected: 2 tests PASSED.

- [ ] **Step 5: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add backend/app/services/zotero_service.py tests/unit/test_zotero_service.py
git commit -m "feat: add zotero_service with normalize_metadata"
```

---

## Task 2: `list_collections` and `list_items`

**Files:**
- Modify: `backend/app/services/zotero_service.py`
- Modify: `tests/unit/test_zotero_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_zotero_service.py`:

```python
from unittest.mock import patch, MagicMock
from app.services.zotero_service import list_collections, list_items


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


def test_list_collections():
    fake_response = [
        {"key": "COL1", "data": {"name": "My Papers"}},
        {"key": "COL2", "data": {"name": "Reading List"}},
    ]
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = _mock_response(fake_response)
        result = list_collections(user_id="12345", api_key="testkey")
    assert result == [
        {"key": "COL1", "name": "My Papers"},
        {"key": "COL2", "name": "Reading List"},
    ]


def test_list_items_cloud_attachment():
    fake_items = [
        {
            "key": "ITEM1",
            "data": {
                "itemType": "journalArticle",
                "title": "Test Paper",
                "creators": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
                "date": "2022",
                "DOI": "10.1234/test",
                "publicationTitle": "Science",
                "abstractNote": "Abstract here.",
            },
        }
    ]
    fake_children = [
        {
            "key": "ATT1",
            "data": {
                "itemType": "attachment",
                "contentType": "application/pdf",
                "linkMode": "imported_file",
                "filename": "test.pdf",
                "path": None,
            },
        }
    ]
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = [
            _mock_response(fake_items),
            _mock_response(fake_children),
        ]
        result = list_items(user_id="12345", api_key="testkey", collection_key="COL1")
    assert len(result) == 1
    assert result[0]["item_key"] == "ITEM1"
    assert result[0]["title"] == "Test Paper"
    assert result[0]["authors"] == ["Jane Doe"]
    assert result[0]["attachment"]["type"] == "cloud"
    assert result[0]["attachment"]["filename"] == "test.pdf"
    assert result[0]["attachment"]["attachment_key"] == "ATT1"


def test_list_items_linked_attachment():
    fake_items = [
        {
            "key": "ITEM2",
            "data": {
                "itemType": "journalArticle",
                "title": "Linked Paper",
                "creators": [],
                "date": "2021",
                "DOI": None,
                "publicationTitle": None,
                "abstractNote": None,
            },
        }
    ]
    fake_children = [
        {
            "key": "ATT2",
            "data": {
                "itemType": "attachment",
                "contentType": "application/pdf",
                "linkMode": "linked_file",
                "filename": "linked.pdf",
                "path": "/home/user/papers/linked.pdf",
            },
        }
    ]
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = [
            _mock_response(fake_items),
            _mock_response(fake_children),
        ]
        result = list_items(user_id="12345", api_key="testkey", collection_key="COL1")
    assert result[0]["attachment"]["type"] == "linked"
    assert result[0]["attachment"]["path"] == "/home/user/papers/linked.pdf"


def test_list_items_no_pdf_attachment():
    """Items with no PDF attachment are excluded from results."""
    fake_items = [
        {
            "key": "ITEM3",
            "data": {"itemType": "journalArticle", "title": "No PDF", "creators": [],
                     "date": None, "DOI": None, "publicationTitle": None, "abstractNote": None},
        }
    ]
    fake_children = [
        {"key": "NOTE1", "data": {"itemType": "note", "contentType": "text/html"}},
    ]
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = [
            _mock_response(fake_items),
            _mock_response(fake_children),
        ]
        result = list_items(user_id="12345", api_key="testkey", collection_key="COL1")
    assert result == []
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_zotero_service.py -v
```
Expected: `ImportError` for `list_collections`, `list_items`.

- [ ] **Step 3: Implement `list_collections` and `list_items` in `zotero_service.py`**

Append to `backend/app/services/zotero_service.py`:

```python
def _headers(api_key: str) -> dict:
    return {"Zotero-API-Key": api_key, "Zotero-API-Version": "3"}


def list_collections(user_id: str, api_key: str) -> list[dict]:
    """Fetch all Zotero collections for the user. Returns [{ key, name }]."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{ZOTERO_API_BASE}/users/{user_id}/collections",
            headers=_headers(api_key),
        )
        resp.raise_for_status()
    return [{"key": c["key"], "name": c["data"]["name"]} for c in resp.json()]


def _parse_author(creator: dict) -> str:
    """Build a full name string from a Zotero creator dict."""
    first = creator.get("firstName", "")
    last = creator.get("lastName", "")
    if first and last:
        return f"{first} {last}"
    return last or first or creator.get("name", "")


def _pick_attachment(children: list[dict]) -> dict | None:
    """Pick the best PDF attachment from a list of children.

    Preference: first cloud attachment, then first linked attachment.
    Returns None if no PDF attachment exists.
    """
    cloud = None
    linked = None
    for child in children:
        data = child.get("data", {})
        if data.get("itemType") != "attachment":
            continue
        if data.get("contentType") != "application/pdf":
            continue
        link_mode = data.get("linkMode", "")
        if link_mode in ("imported_file", "imported_url") and cloud is None:
            cloud = child
        elif link_mode == "linked_file" and linked is None:
            linked = child
    chosen = cloud or linked
    if not chosen:
        return None
    data = chosen["data"]
    link_mode = data.get("linkMode", "")
    return {
        "type": "cloud" if link_mode in ("imported_file", "imported_url") else "linked",
        "filename": data.get("filename") or data.get("title", "attachment.pdf"),
        "attachment_key": chosen["key"],
        "path": data.get("path"),
    }


def list_items(user_id: str, api_key: str, collection_key: str) -> list[dict]:
    """Fetch all items in a Zotero collection with their PDF attachment info."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{ZOTERO_API_BASE}/users/{user_id}/collections/{collection_key}/items",
            headers=_headers(api_key),
            params={"itemType": "journalArticle || book || bookSection || conferencePaper || preprint || thesis || report"},
        )
        resp.raise_for_status()
        items_raw = resp.json()

        result = []
        for item in items_raw:
            ikey = item["key"]
            data = item["data"]

            # Fetch children (attachments, notes)
            children_resp = client.get(
                f"{ZOTERO_API_BASE}/users/{user_id}/items/{ikey}/children",
                headers=_headers(api_key),
            )
            children_resp.raise_for_status()
            attachment = _pick_attachment(children_resp.json())
            if not attachment:
                continue  # Skip items with no PDF

            creators = data.get("creators", [])
            year_raw = data.get("date") or ""
            year = None
            for part in str(year_raw).split("-"):
                if len(part) == 4 and part.isdigit():
                    year = int(part)
                    break

            result.append({
                "item_key": ikey,
                "title": data.get("title"),
                "authors": [_parse_author(c) for c in creators if c.get("creatorType") == "author"],
                "year": year,
                "doi": data.get("DOI"),
                "journal": data.get("publicationTitle"),
                "abstract": data.get("abstractNote"),
                "attachment": attachment,
            })

    return result
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_zotero_service.py -v
```
Expected: all tests PASSED.

- [ ] **Step 5: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add backend/app/services/zotero_service.py tests/unit/test_zotero_service.py
git commit -m "feat: add list_collections and list_items to zotero_service"
```

---

## Task 3: `download_pdf` with 429 retry

**Files:**
- Modify: `backend/app/services/zotero_service.py`
- Modify: `tests/unit/test_zotero_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_zotero_service.py`:

```python
from app.services.zotero_service import download_pdf


def test_download_pdf_success():
    fake_pdf_bytes = b"%PDF-1.4 fake"
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_pdf_bytes
        mock_resp.raise_for_status = MagicMock()
        instance.get.return_value = mock_resp
        result = download_pdf(user_id="12345", api_key="testkey", attachment_key="ATT1")
    assert result == fake_pdf_bytes


def test_download_pdf_retries_on_429():
    """Should retry once on 429 and succeed on second attempt."""
    fake_pdf_bytes = b"%PDF-1.4 retried"
    with patch("httpx.Client") as MockClient:
        with patch("time.sleep"):  # Don't actually sleep in tests
            instance = MockClient.return_value.__enter__.return_value
            # First call: 429, second call: 200
            rate_limit = MagicMock()
            rate_limit.status_code = 429
            rate_limit.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429", request=MagicMock(), response=rate_limit
            )
            success = MagicMock()
            success.status_code = 200
            success.content = fake_pdf_bytes
            success.raise_for_status = MagicMock()
            instance.get.side_effect = [rate_limit, success]
            result = download_pdf(user_id="12345", api_key="testkey", attachment_key="ATT1")
    assert result == fake_pdf_bytes


def test_download_pdf_raises_on_double_429():
    """Should raise after two consecutive 429 responses."""
    import pytest
    with patch("httpx.Client") as MockClient:
        with patch("time.sleep"):
            instance = MockClient.return_value.__enter__.return_value
            rate_limit = MagicMock()
            rate_limit.status_code = 429
            rate_limit.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429", request=MagicMock(), response=rate_limit
            )
            instance.get.return_value = rate_limit
            with pytest.raises(httpx.HTTPStatusError):
                download_pdf(user_id="12345", api_key="testkey", attachment_key="ATT1")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_zotero_service.py::test_download_pdf_success -v
```
Expected: `ImportError` for `download_pdf`.

- [ ] **Step 3: Implement `download_pdf` in `zotero_service.py`**

Append to `backend/app/services/zotero_service.py`:

```python
def download_pdf(user_id: str, api_key: str, attachment_key: str) -> bytes:
    """Download a PDF attachment from Zotero cloud storage.

    Retries once with exponential backoff on HTTP 429 (rate limited).
    Raises httpx.HTTPStatusError on second 429 or other HTTP errors.
    """
    url = f"{ZOTERO_API_BASE}/users/{user_id}/items/{attachment_key}/file"
    with httpx.Client(timeout=60.0) as client:
        for attempt in range(2):
            try:
                resp = client.get(url, headers=_headers(api_key))
                resp.raise_for_status()
                return resp.content
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt == 0:
                    time.sleep(2 ** attempt * 2)  # 2s backoff
                    continue
                raise
    # unreachable, but satisfies type checker
    raise RuntimeError("download_pdf: exhausted retries")
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_zotero_service.py -v
```
Expected: all tests PASSED.

- [ ] **Step 5: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add backend/app/services/zotero_service.py tests/unit/test_zotero_service.py
git commit -m "feat: add download_pdf with 429 retry to zotero_service"
```

---

## Task 4: Preprocessing service guard

**Files:**
- Modify: `backend/app/services/preprocessing_service.py` (lines 94–116)
- Modify: `tests/unit/test_preprocessing_service.py`

The goal: when `{stem}_metadata.json` already exists in the preprocessed dir before `convert_single_pdf` runs, skip the enrichment API call AND skip the normal metadata write. Instead, read the existing file, merge in `backend` and `preprocessed_at`, then write it back.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_preprocessing_service.py`:

```python
def test_convert_skips_enrichment_when_metadata_exists(service, temp_dirs):
    """If _metadata.json exists before convert, enrichment is skipped and file is preserved."""
    pdf_input, preprocessed = temp_dirs
    dir_name = "zotero_test_zt"
    # Create input dir and fake PDF
    input_dir = Path(pdf_input) / dir_name
    input_dir.mkdir()
    pdf_path = input_dir / "mypaper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    # Pre-write a metadata file (simulating Zotero import)
    output_dir = Path(preprocessed) / dir_name
    output_dir.mkdir(parents=True)
    meta_path = output_dir / "mypaper_metadata.json"
    zotero_meta = {
        "title": "Zotero Title",
        "authors": ["Alice"],
        "publication_date": "2023",
        "metadata_source": "zotero",
        "source_pdf": "mypaper.pdf",
    }
    meta_path.write_text(json.dumps(zotero_meta), encoding="utf-8")

    with patch("app.services.preprocessing_service._api_enrich") as mock_enrich, \
         patch("app.services.preprocessing_service.get_converter") as mock_conv:
        mock_converter = MagicMock()
        mock_converter.convert_and_extract.return_value = ("# Markdown content", {"title": "Extracted"})
        mock_conv.return_value = mock_converter

        result = service.convert_single_pdf(dir_name, "mypaper.pdf", backend="pymupdf", metadata_backend="openalex")

    # Enrichment API must NOT have been called
    mock_enrich.assert_not_called()

    # Metadata file must preserve Zotero data and gain backend + preprocessed_at
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved["title"] == "Zotero Title"
    assert saved["metadata_source"] == "zotero"
    assert saved["backend"] == "pymupdf"
    assert "preprocessed_at" in saved

    # Markdown file must have been written
    md_path = output_dir / "mypaper.md"
    assert md_path.exists()
    assert result["metadata_enriched"] is False
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_preprocessing_service.py::test_convert_skips_enrichment_when_metadata_exists -v
```
Expected: FAIL — enrichment is called even though metadata exists.

- [ ] **Step 3: Apply the guard to `convert_single_pdf`**

In `backend/app/services/preprocessing_service.py`, replace the metadata block (lines 93–116) with:

```python
        # Write metadata (with paper info, but no tables/images yet)
        metadata = {
            **paper_meta,
            "source_pdf": filename,
            "backend": backend,
            "preprocessed_at": datetime.now(UTC).isoformat(),
        }

        # Check for pre-existing metadata (e.g. written by Zotero import)
        metadata_path = output_dir / f"{stem}_metadata.json"
        enriched = False
        if metadata_path.exists():
            # Preserve existing metadata; only merge in backend + preprocessed_at
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            existing["backend"] = backend
            existing["preprocessed_at"] = metadata["preprocessed_at"]
            metadata_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        else:
            # Auto-enrich with metadata API
            if metadata_backend and metadata_backend != "none":
                title = paper_meta.get("title", stem)
                api_data = _api_enrich(title, metadata_backend)
                if api_data:
                    for key in ("title", "authors", "publication_date", "abstract", "doi", "journal"):
                        if api_data.get(key):
                            metadata[key] = api_data[key]
                    if api_data.get("openalex_id"):
                        metadata["openalex_id"] = api_data["openalex_id"]
                    metadata["metadata_source"] = metadata_backend
                    enriched = True
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run all preprocessing tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/unit/test_preprocessing_service.py -v
```
Expected: all tests PASSED (including existing tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add backend/app/services/preprocessing_service.py tests/unit/test_preprocessing_service.py
git commit -m "feat: skip metadata enrichment in convert when _metadata.json already exists"
```

---

## Task 5: Settings changes

**Files:**
- Modify: `config.yaml`
- Modify: `backend/app/api/settings.py`

- [ ] **Step 1: Add `zotero` section to `config.yaml`**

```yaml
# append to config.yaml
zotero:
  user_id: ""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/integration/test_settings_api.py`:

```python
# tests/integration/test_settings_api.py
import sys
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_get_settings_includes_zotero_fields(client):
    with patch("app.api.settings._api_keys") as mock_keys:
        mock_keys.has_key.side_effect = lambda p: p == "anthropic"
        resp = client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "zotero_user_id" in data
    assert "has_zotero_key" in data
    assert isinstance(data["has_zotero_key"], bool)


def test_post_settings_saves_zotero_user_id(client, tmp_path):
    config_path = tmp_path / "config.yaml"
    import yaml
    config_path.write_text(yaml.dump({
        "models": {"embedding": "nomic", "llm": {"type": "local", "model": "llama3.2"}},
        "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
        "retrieval": {"top_k": 10},
        "zotero": {"user_id": ""},
    }))
    with patch("app.api.settings.CONFIG_PATH", config_path), \
         patch("app.api.settings._api_keys") as mock_keys:
        mock_keys.has_key.return_value = False
        resp = client.post("/settings", json={"zotero_user_id": "99887766"})
    assert resp.status_code == 200
    saved = yaml.safe_load(config_path.read_text())
    assert saved["zotero"]["user_id"] == "99887766"


def test_post_settings_saves_zotero_key(client, tmp_path):
    config_path = tmp_path / "config.yaml"
    import yaml
    config_path.write_text(yaml.dump({
        "models": {"embedding": "nomic", "llm": {"type": "local", "model": "llama3.2"}},
        "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
        "retrieval": {"top_k": 10},
    }))
    with patch("app.api.settings.CONFIG_PATH", config_path), \
         patch("app.api.settings._api_keys") as mock_keys:
        resp = client.post("/settings", json={"zotero_key": "secret_key_123"})
    assert resp.status_code == 200
    mock_keys.set_key.assert_called_once_with("zotero", "secret_key_123")
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/integration/test_settings_api.py -v
```
Expected: FAIL — `zotero_user_id` not in response yet.

- [ ] **Step 4: Update `backend/app/api/settings.py`**

**a)** Add to `UpdateSettingsRequest` after `clear_google_key`:
```python
zotero_user_id: Optional[str] = None
zotero_key: Optional[str] = None     # write-only — never returned
clear_zotero_key: bool = False
```

**b)** In `get_settings()`, add to the returned dict:
```python
"zotero_user_id": config.get("zotero", {}).get("user_id", ""),
"has_zotero_key": _api_keys.has_key("zotero"),
```

**c)** In `update_settings()`, after the Google key block, add:
```python
if request.zotero_user_id is not None:
    if "zotero" not in config:
        config["zotero"] = {}
    config["zotero"]["user_id"] = request.zotero_user_id

# (inside the yaml.dump block — no change needed there)

if request.clear_zotero_key:
    _api_keys.clear_key("zotero")
elif request.zotero_key:
    _api_keys.set_key("zotero", request.zotero_key)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/integration/test_settings_api.py -v
```
Expected: all tests PASSED.

- [ ] **Step 6: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add config.yaml backend/app/api/settings.py tests/integration/test_settings_api.py
git commit -m "feat: add zotero_user_id and zotero_key to settings"
```

---

## Task 6: Zotero API router

**Files:**
- Create: `backend/app/api/zotero.py`
- Create: `tests/integration/test_zotero_api.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/integration/test_zotero_api.py -v
```
Expected: `ImportError` — router not registered yet.

- [ ] **Step 3: Create `backend/app/api/zotero.py`**

```python
# backend/app/api/zotero.py
"""Zotero integration API endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings, load_config
from app.services.api_keys_service import ApiKeysService
from app.services import zotero_service
from app.services.zotero_service import normalize_metadata

router = APIRouter()
_api_keys = ApiKeysService()
_CONFIG_PATH = Path("config.yaml")


def _get_user_id() -> str:
    config = load_config(str(_CONFIG_PATH))
    return config.get("zotero", {}).get("user_id", "")


def _require_credentials():
    """Return (user_id, api_key) or raise 400."""
    user_id = _get_user_id()
    api_key = _api_keys.get_key("zotero")
    if not user_id or not api_key:
        raise HTTPException(
            status_code=400,
            detail="Zotero user ID or API key not configured. Go to Settings.",
        )
    return user_id, api_key


@router.get("/zotero/collections")
def list_collections():
    """List all Zotero collections for the configured user."""
    user_id, api_key = _require_credentials()
    try:
        return zotero_service.list_collections(user_id, api_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/zotero/collections/{collection_key}/items")
def list_items(collection_key: str):
    """List items with PDF attachments in a Zotero collection."""
    user_id, api_key = _require_credentials()
    try:
        return zotero_service.list_items(user_id, api_key, collection_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class ImportRequest(BaseModel):
    collection_key: str
    dir_name: str
    item_keys: list[str]


@router.post("/zotero/import")
def import_from_zotero(request: ImportRequest):
    """Download selected Zotero PDFs and pre-write metadata. Streams SSE progress."""
    user_id, api_key = _require_credentials()

    # Sanitize dir_name and apply _zt suffix
    safe_dir = Path(request.dir_name).name
    dir_name = f"{safe_dir}_zt"

    pdf_dir  = Path(settings.pdf_input_dir)  / dir_name
    prep_dir = Path(settings.preprocessed_dir) / dir_name
    pdf_dir.mkdir(parents=True, exist_ok=True)
    prep_dir.mkdir(parents=True, exist_ok=True)

    # Build item_key → item map from the collection
    try:
        all_items = zotero_service.list_items(user_id, api_key, request.collection_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    items_map = {item["item_key"]: item for item in all_items}
    selected = [items_map[k] for k in request.item_keys if k in items_map]

    def generate():
        for item in selected:
            attachment = item.get("attachment") or {}
            filename = attachment.get("filename", "attachment.pdf")
            stem = Path(filename).stem

            pdf_path  = pdf_dir  / filename
            meta_path = prep_dir / f"{stem}_metadata.json"

            # Skip if PDF already exists (idempotent re-import)
            if pdf_path.exists():
                yield f"data: {json.dumps({'filename': filename, 'status': 'skipped'})}\n\n"
                continue

            yield f"data: {json.dumps({'filename': filename, 'status': 'downloading'})}\n\n"
            try:
                pdf_bytes = zotero_service.download_pdf(user_id, api_key, attachment["attachment_key"])
                pdf_path.write_bytes(pdf_bytes)
                # Write pre-filled Zotero metadata
                metadata = normalize_metadata(item)
                meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                yield f"data: {json.dumps({'filename': filename, 'status': 'done'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'filename': filename, 'status': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

```python
# Add this import at the top with the other api imports:
from app.api import zotero

# Add this line with the other include_router calls:
app.include_router(zotero.router, tags=["zotero"])
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/integration/test_zotero_api.py -v
```
Expected: all tests PASSED.

- [ ] **Step 6: Run the full test suite**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/ -v --ignore=tests/unit/test_docling_service.py
```
Expected: all tests PASSED (docling skipped — requires heavy model).

- [ ] **Step 7: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add backend/app/api/zotero.py backend/app/main.py tests/integration/test_zotero_api.py
git commit -m "feat: add Zotero API endpoints (list collections, list items, import SSE)"
```

---

## Task 7: Frontend — Settings tab

**Files:**
- Modify: `frontend-web/js/app.js`

The settings form in `app.js` uses a `settingsForm` reactive object. The Zotero fields follow the exact same pattern as Anthropic/Google keys.

- [ ] **Step 1: Add Zotero fields to `settingsForm` reactive object**

In `app.js`, inside the `settingsForm` reactive object (after `clearGoogleKey`), add:
```javascript
zoteroUserId:    '',
zoteroKey:       '',
hasZoteroKey:    false,
clearZoteroKey:  false,
```

- [ ] **Step 2: Load Zotero fields in `openSettings()`**

In `openSettings()`, after `settingsForm.clearGoogleKey = false`, add:
```javascript
settingsForm.zoteroUserId   = cfg.zotero_user_id || ''
settingsForm.hasZoteroKey   = !!cfg.has_zotero_key
settingsForm.zoteroKey      = ''
settingsForm.clearZoteroKey = false
```

- [ ] **Step 3: Save Zotero fields in `saveSettings()`**

In `saveSettings()`, after the Google key block (`if (settingsForm.llmProvider === 'google') {...}`), add:
```javascript
if (settingsForm.zoteroUserId.trim())
  body.zotero_user_id = settingsForm.zoteroUserId.trim()
if (settingsForm.clearZoteroKey)
  body.clear_zotero_key = true
else if (settingsForm.zoteroKey.trim())
  body.zotero_key = settingsForm.zoteroKey.trim()
```

- [ ] **Step 4: Add Zotero fields to the settings modal template**

In the settings modal template (search for `hasGoogleKey` in the template to find the Google key block), add a Zotero section immediately after the Google block, following the same markup pattern:

```html
<!-- Zotero -->
<div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border)">
  <div style="font-weight:600;font-size:13px;margin-bottom:8px">Zotero</div>
  <div class="form-group">
    <label class="form-label">Zotero User ID</label>
    <input v-model="settingsForm.zoteroUserId" class="form-control" placeholder="e.g. 1234567" />
  </div>
  <div class="form-group" style="margin-top:8px">
    <label class="form-label">Zotero API Key</label>
    <div v-if="settingsForm.hasZoteroKey && !settingsForm.clearZoteroKey"
         class="flex items-center gap-8">
      <span style="color:var(--success);font-size:13px">✓ Key saved</span>
      <button class="btn btn-sm btn-danger"
              @click="settingsForm.clearZoteroKey = true">Clear</button>
    </div>
    <div v-else>
      <input v-model="settingsForm.zoteroKey" type="password"
             class="form-control" placeholder="Paste API key" />
      <div v-if="settingsForm.clearZoteroKey"
           style="font-size:12px;color:var(--danger);margin-top:4px">
        Key will be cleared on save.
        <a href="#" @click.prevent="settingsForm.clearZoteroKey=false">Undo</a>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 5: Manual verification**

Open the app in a browser, go to Settings. Verify:
- "Zotero" section appears below Google
- Zotero User ID input saves correctly (enter a value, save, reopen settings)
- API Key field shows `✓ Key saved` after saving a key, with a "Clear" button

- [ ] **Step 6: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add frontend-web/js/app.js
git commit -m "feat: add Zotero User ID and API Key fields to settings"
```

---

## Task 8: Frontend — PDF tab Zotero import panel

**Files:**
- Modify: `frontend-web/js/pdf-tab.js`

- [ ] **Step 1: Add reactive state for the Zotero panel**

In `pdf-tab.js`, in the `setup()` function, after the existing reactive state declarations (after `expandedFiles`, `fileMetadata` etc.), add:

```javascript
// Zotero import panel state
const showZotero       = ref(false)
const ztCollections    = ref([])
const ztCollError      = ref(null)
const ztSelCollection  = ref(null)
const ztItems          = ref([])
const ztItemsLoading   = ref(false)
const ztItemsError     = ref(null)
const ztChecked        = reactive({})   // item_key → true/false
const ztDirName        = ref('')
const ztImporting      = ref(false)
const ztProgress       = reactive({})   // filename → { status, message }
const ztDone           = ref(false)
const ztImportError    = ref(null)
```

- [ ] **Step 2: Add Zotero panel functions**

In `setup()`, after the existing functions, add:

```javascript
async function openZoteroPanel() {
  showZotero.value     = true
  ztCollections.value  = []
  ztCollError.value    = null
  ztSelCollection.value = null
  ztItems.value        = []
  ztDone.value         = false
  ztImportError.value  = null
  try {
    ztCollections.value = await api.get('/zotero/collections')
  } catch (e) {
    ztCollError.value = e.message
  }
}

async function selectZoteroCollection(collKey, collName) {
  ztSelCollection.value = { key: collKey, name: collName }
  ztDirName.value       = collName.toLowerCase().replace(/\s+/g, '_')
  ztItems.value         = []
  ztItemsError.value    = null
  ztItemsLoading.value  = true
  Object.keys(ztChecked).forEach(k => delete ztChecked[k])
  try {
    const items = await api.get(`/zotero/collections/${collKey}/items`)
    ztItems.value = items
    // Pre-check all cloud items
    for (const item of items) {
      if (item.attachment?.type === 'cloud') ztChecked[item.item_key] = true
    }
  } catch (e) {
    ztItemsError.value = e.message
  } finally {
    ztItemsLoading.value = false
  }
}

async function runZoteroImport() {
  const selectedKeys = Object.entries(ztChecked)
    .filter(([, v]) => v)
    .map(([k]) => k)
  if (!selectedKeys.length) return
  ztImporting.value   = true
  ztDone.value        = false
  ztImportError.value = null
  Object.keys(ztProgress).forEach(k => delete ztProgress[k])
  try {
    const resp = await fetch(`${api.url()}/zotero/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        collection_key: ztSelCollection.value.key,
        dir_name:       ztDirName.value,
        item_keys:      selectedKeys,
      }),
    })
    const reader  = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = JSON.parse(line.slice(6))
        if (data.done) { ztDone.value = true; break }
        if (data.filename) ztProgress[data.filename] = { status: data.status, message: data.message }
      }
    }
  } catch (e) {
    ztImportError.value = e.message
  } finally {
    ztImporting.value = false
    if (ztDone.value) {
      for (const k of Object.keys(dirFiles)) delete dirFiles[k]
      await loadDirs()
    }
  }
}
```

- [ ] **Step 3: Expose new state and functions in the `return` statement**

Add to the `return { ... }` object at the end of `setup()`:
```javascript
showZotero, ztCollections, ztCollError, ztSelCollection,
ztItems, ztItemsLoading, ztItemsError,
ztChecked, ztDirName, ztImporting, ztProgress, ztDone, ztImportError,
openZoteroPanel, selectZoteroCollection, runZoteroImport,
```

- [ ] **Step 4: Add the Zotero import panel to the template**

In the template, find the upload section (the `<input type="file">` block) and add the Zotero button and panel alongside it. The upload section starts around where `uploadDir` is used. Add after the upload row:

```html
<!-- Zotero import button -->
<button class="btn btn-secondary" style="margin-left:8px" @click="openZoteroPanel">
  Import from Zotero
</button>

<!-- Zotero import panel -->
<div v-if="showZotero" class="card" style="margin-top:12px">
  <div style="font-weight:600;font-size:14px;margin-bottom:12px">
    Import from Zotero
    <button class="btn btn-sm" style="float:right" @click="showZotero=false">✕</button>
  </div>

  <div v-if="ztCollError" class="alert alert-error">
    {{ ztCollError }}
    <span v-if="ztCollError.includes('not configured')"> — Go to Settings to add your Zotero credentials.</span>
  </div>

  <div v-else-if="ztCollections.length === 0" class="text-muted text-sm">Loading collections…</div>

  <div v-else>
    <!-- Collection picker -->
    <div class="form-group">
      <label class="form-label">Collection</label>
      <select class="form-control"
              @change="e => selectZoteroCollection(e.target.value, ztCollections.find(c=>c.key===e.target.value)?.name || '')">
        <option value="">— select a collection —</option>
        <option v-for="c in ztCollections" :key="c.key" :value="c.key">{{ c.name }}</option>
      </select>
    </div>

    <!-- Item list -->
    <div v-if="ztItemsLoading" class="text-muted text-sm">Loading papers…</div>
    <div v-else-if="ztItemsError" class="alert alert-error">{{ ztItemsError }}</div>
    <div v-else-if="ztItems.length">
      <div style="max-height:260px;overflow-y:auto;margin:8px 0;border:1px solid var(--border);border-radius:4px">
        <label v-for="item in ztItems" :key="item.item_key"
               :style="item.attachment.type === 'linked'
                 ? 'display:flex;align-items:flex-start;gap:8px;padding:8px 12px;opacity:.5;cursor:default'
                 : 'display:flex;align-items:flex-start;gap:8px;padding:8px 12px;cursor:pointer'">
          <input type="checkbox"
                 :disabled="item.attachment.type === 'linked'"
                 :checked="!!ztChecked[item.item_key]"
                 @change="e => ztChecked[item.item_key] = e.target.checked"
                 style="margin-top:2px" />
          <div>
            <div style="font-size:13px;font-weight:500">{{ item.title }}</div>
            <div style="font-size:11px;color:var(--text-muted)">
              {{ (item.authors || []).slice(0,2).join(', ') }}
              <span v-if="(item.authors||[]).length > 2"> et al.</span>
              <span v-if="item.year"> · {{ item.year }}</span>
            </div>
            <div v-if="item.attachment.type === 'linked'"
                 style="font-size:11px;color:var(--warning);margin-top:2px">
              ⚠ Linked file — upload manually from <code>{{ item.attachment.path }}</code>
            </div>
            <!-- Progress status -->
            <div v-if="ztProgress[item.attachment.filename]" style="font-size:11px;margin-top:2px">
              <span v-if="ztProgress[item.attachment.filename].status === 'downloading'">
                <span class="spinner" style="width:10px;height:10px;border-width:2px"></span> Downloading…
              </span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'done'"
                    style="color:var(--success)">✓ Imported</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'skipped'"
                    style="color:var(--success)">✓ Skipped (already imported)</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'error'"
                    style="color:var(--danger)">✗ {{ ztProgress[item.attachment.filename].message }}</span>
            </div>
          </div>
        </label>
      </div>

      <!-- Directory name + import button -->
      <div class="form-group" style="margin-bottom:8px">
        <label class="form-label">Directory name
          <span style="font-size:11px;color:var(--text-muted)"> (<code>_zt</code> will be appended)</span>
        </label>
        <input v-model="ztDirName" class="form-control" placeholder="collection_name" />
      </div>

      <div v-if="ztImportError" class="alert alert-error" style="margin-bottom:8px">{{ ztImportError }}</div>

      <button class="btn btn-primary"
              :disabled="ztImporting || !ztDirName.trim() || !Object.values(ztChecked).some(Boolean)"
              @click="runZoteroImport">
        <span v-if="ztImporting"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> Importing…</span>
        <span v-else>Import selected</span>
      </button>

      <div v-if="ztDone" style="color:var(--success);font-size:13px;margin-top:8px">
        ✓ Import complete. PDFs are ready to convert.
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 5: Manual verification**

1. Open the app, go to PDF Management
2. Click "Import from Zotero" — should show error if credentials not set, or load collections if set
3. With valid credentials: select a collection, verify cloud items are checked, linked items are greyed out with path
4. Enter a directory name, click Import
5. Verify progress updates per file (spinner → ✓)
6. After import: directory `{name}_zt` appears in the directory list
7. Re-import the same collection: all files show `✓ Skipped (already imported)`
8. Convert a Zotero-imported PDF — verify metadata is pre-filled from Zotero (no enrichment call)

- [ ] **Step 6: Commit**

```bash
cd /Users/jose/Repos/PRAG-v2
git add frontend-web/js/pdf-tab.js
git commit -m "feat: add Zotero import panel to PDF tab"
```

---

## Final verification

- [ ] **Run full test suite**

```bash
cd /Users/jose/Repos/PRAG-v2 && pytest tests/ -v --ignore=tests/unit/test_docling_service.py
```
Expected: all tests PASSED.

- [ ] **End-to-end smoke test** (requires running stack)

```bash
docker compose up -d
```

1. Open app → Settings → add Zotero User ID + API Key → Save
2. PDF Management → Import from Zotero → select a collection with cloud PDFs → Import
3. Verify `_zt` directory appears with PDFs
4. Convert one PDF — check metadata panel shows `metadata_source: zotero` and correct title/authors
5. Ingest into a collection
6. RAG query against the collection
