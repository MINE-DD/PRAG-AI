import os
from typing import Optional

import streamlit as st
import httpx

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Backend helper functions
# ---------------------------------------------------------------------------

def check_backend_health() -> dict:
    """Check if backend is healthy"""
    try:
        response = httpx.get(f"{BACKEND_URL}/health", timeout=5.0)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def get_collections() -> list:
    """Fetch all collections"""
    try:
        response = httpx.get(f"{BACKEND_URL}/collections")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching collections: {e}")
        return []


def get_papers(collection_id: str) -> list:
    """Fetch papers in a collection"""
    try:
        response = httpx.get(f"{BACKEND_URL}/collections/{collection_id}/papers")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching papers: {e}")
        return []


def get_paper_detail(collection_id: str, paper_id: str) -> dict | None:
    """Fetch full metadata for a single paper from the collection."""
    try:
        response = httpx.get(f"{BACKEND_URL}/collections/{collection_id}/papers/{paper_id}", timeout=10.0)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def rag_query(
    collection_id: str,
    query_text: str,
    paper_ids: list = None,
    include_citations: bool = False,
    limit: int = 10,
    max_tokens: int = 500,
    use_hybrid: bool = False,
) -> Optional[dict]:
    """RAG query: retrieve and generate answer from papers"""
    try:
        payload = {
            "query_text": query_text,
            "limit": limit,
            "max_tokens": max_tokens,
            "include_citations": include_citations,
            "use_hybrid": use_hybrid,
        }
        if paper_ids:
            payload["paper_ids"] = paper_ids

        response = httpx.post(
            f"{BACKEND_URL}/collections/{collection_id}/rag",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error querying papers: {e}")
        return None


def summarize_papers(collection_id: str, paper_ids: list, max_tokens: Optional[int] = None) -> Optional[dict]:
    """Summarize papers"""
    try:
        payload = {"paper_ids": paper_ids}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = httpx.post(
            f"{BACKEND_URL}/collections/{collection_id}/summarize",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error summarizing papers: {e}")
        return None


def compare_papers(collection_id: str, paper_ids: list, aspect: str = "all", max_tokens: Optional[int] = None) -> Optional[dict]:
    """Compare papers"""
    try:
        payload = {"paper_ids": paper_ids, "aspect": aspect}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = httpx.post(
            f"{BACKEND_URL}/collections/{collection_id}/compare",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error comparing papers: {e}")
        return None


def export_to_markdown(content_type: str, data: dict, query_text: str = "") -> str:
    """Export results to markdown format"""
    md_lines = ["# PRAG-v2 Export", "", f"**Generated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]

    if content_type == "search":
        md_lines.append(f"## Query: {query_text}")
        md_lines.append("")
        md_lines.append(f"**Found {len(data.get('results', []))} relevant passages**")
        md_lines.append("")

        for i, result in enumerate(data.get("results", []), 1):
            md_lines.append(f"### Result {i} (Score: {result['score']:.3f})")
            md_lines.append("")
            md_lines.append(f"> {result['chunk_text']}")
            md_lines.append("")
            md_lines.append(f"*Source: {result['unique_id']} | Page: {result['page_number']} | Type: {result['chunk_type']}*")
            md_lines.append("")

        if "citations" in data:
            md_lines.append("## Citations")
            md_lines.append("")
            for paper_id, citation in data["citations"].items():
                md_lines.append(f"### {citation['unique_id']}")
                md_lines.append("")
                md_lines.append(f"**Title:** {citation['title']}")
                md_lines.append(f"**Authors:** {', '.join(citation['authors'])}")
                md_lines.append(f"**Year:** {citation.get('year', 'N/A')}")
                md_lines.append("")
                md_lines.append("**APA Citation:**")
                md_lines.append(f"> {citation['apa']}")
                md_lines.append("")
                md_lines.append("**BibTeX:**")
                md_lines.append("```bibtex")
                md_lines.append(citation['bibtex'])
                md_lines.append("```")
                md_lines.append("")

    elif content_type == "summary":
        md_lines.append("## Summary")
        md_lines.append("")
        md_lines.append(data.get("summary", ""))
        md_lines.append("")
        md_lines.append("### Papers Summarized")
        md_lines.append("")
        for paper in data.get("papers", []):
            md_lines.append(f"- **{paper['title']}** ({paper.get('year', 'N/A')}) - {', '.join(paper['authors'])}")
        md_lines.append("")

    elif content_type == "comparison":
        md_lines.append("## Paper Comparison")
        md_lines.append("")
        md_lines.append(data.get("comparison", ""))
        md_lines.append("")
        md_lines.append("### Papers Compared")
        md_lines.append("")
        for paper in data.get("papers", []):
            md_lines.append(f"- **{paper['title']}** ({paper.get('year', 'N/A')}) - {', '.join(paper['authors'])}")
        md_lines.append("")

    md_lines.append("---")
    md_lines.append("*Generated by PRAG-v2*")

    return "\n".join(md_lines)
