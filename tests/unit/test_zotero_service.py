import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from unittest.mock import MagicMock, patch

from app.services.zotero_service import list_collections, list_items, normalize_metadata


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


import httpx
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
