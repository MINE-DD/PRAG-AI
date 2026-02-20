"""Fetch paper metadata from free academic APIs."""

import httpx


def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Reconstruct abstract from OpenAlex inverted index format."""
    if not inverted_index:
        return None
    words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    words.sort()
    return " ".join(w for _, w in words) if words else None


def fetch_openalex(title: str) -> dict:
    """Search OpenAlex by title and return metadata."""
    resp = httpx.get(
        "https://api.openalex.org/works",
        params={"search": title, "per_page": 1},
        headers={"User-Agent": "PRAG-v2 (mailto:prag@example.com)"},
        timeout=15.0,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return {}
    work = results[0]
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    return {
        "title": work.get("title"),
        "authors": [
            a["author"]["display_name"]
            for a in work.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ],
        "publication_date": work.get("publication_date"),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "doi": work.get("doi"),
        "journal": source.get("display_name"),
        "openalex_id": work.get("id"),
    }


def fetch_crossref(title: str) -> dict:
    """Search CrossRef by title and return metadata."""
    resp = httpx.get(
        "https://api.crossref.org/works",
        params={"query.title": title, "rows": 1},
        headers={"User-Agent": "PRAG-v2 (mailto:prag@example.com)"},
        timeout=15.0,
    )
    resp.raise_for_status()
    items = resp.json().get("message", {}).get("items", [])
    if not items:
        return {}
    item = items[0]

    authors = []
    for a in item.get("author", []):
        name_parts = []
        if a.get("given"):
            name_parts.append(a["given"])
        if a.get("family"):
            name_parts.append(a["family"])
        if name_parts:
            authors.append(" ".join(name_parts))

    pub_date = None
    date_parts = item.get("published-print", item.get("published-online", {})).get("date-parts", [[]])
    if date_parts and date_parts[0]:
        parts = date_parts[0]
        pub_date = "-".join(str(p).zfill(2) for p in parts)

    return {
        "title": item.get("title", [""])[0] if item.get("title") else None,
        "authors": authors,
        "publication_date": pub_date,
        "abstract": item.get("abstract"),
        "doi": item.get("DOI"),
        "journal": item.get("container-title", [""])[0] if item.get("container-title") else None,
    }


def fetch_semantic_scholar(title: str) -> dict:
    """Search Semantic Scholar by title and return metadata."""
    resp = httpx.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": title,
            "limit": 1,
            "fields": "title,authors,year,abstract,externalIds,publicationDate,journal",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        return {}
    paper = data[0]
    return {
        "title": paper.get("title"),
        "authors": [a["name"] for a in paper.get("authors", []) if a.get("name")],
        "publication_date": paper.get("publicationDate"),
        "abstract": paper.get("abstract"),
        "doi": (paper.get("externalIds") or {}).get("DOI"),
        "journal": (paper.get("journal") or {}).get("name"),
    }


BACKENDS = {
    "openalex": fetch_openalex,
    "crossref": fetch_crossref,
    "semantic_scholar": fetch_semantic_scholar,
}


def enrich_metadata(title: str, backend: str) -> dict:
    """Fetch metadata from the specified backend. Returns {} on failure."""
    fn = BACKENDS.get(backend)
    if not fn:
        return {}
    try:
        return fn(title)
    except Exception:
        return {}
