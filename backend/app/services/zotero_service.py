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


def download_pdf(user_id: str, api_key: str, attachment_key: str) -> bytes:
    """Download a PDF attachment from Zotero cloud storage.

    Retries once with exponential backoff on HTTP 429 (rate limited).
    Raises httpx.HTTPStatusError on second 429 or other HTTP errors.
    """
    url = f"{ZOTERO_API_BASE}/users/{user_id}/items/{attachment_key}/file"
    with httpx.Client(timeout=60.0) as client:
        for attempt in range(2):
            try:
                resp = client.get(url, headers=_headers(api_key), follow_redirects=True)
                resp.raise_for_status()
                return resp.content
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt == 0:
                    time.sleep(2 ** attempt * 2)  # 2s backoff
                    continue
                if e.response.status_code == 404:
                    raise RuntimeError(
                        "PDF not found in Zotero cloud — the file may not be synced. "
                        "Enable file sync in Zotero (Edit → Preferences → Sync) or upload the PDF manually."
                    ) from e
                raise
    # unreachable, but satisfies type checker
    raise RuntimeError("download_pdf: exhausted retries")
