import time

import streamlit as st
import httpx
import os
from typing import Optional

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


# ---------------------------------------------------------------------------
# Tab 1: PDF Preprocessing
# ---------------------------------------------------------------------------

def _fetch_pdf_assets(dir_name: str, filename: str) -> dict:
    """Fetch tables/images info for a processed PDF."""
    try:
        resp = httpx.post(
            f"{BACKEND_URL}/preprocess/assets",
            json={"dir_name": dir_name, "filename": filename},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"tables": [], "images": []}


def _render_pdf_assets(dir_name: str, filename: str):
    """Render paper metadata, tables, and images extracted from a processed PDF."""
    assets = _fetch_pdf_assets(dir_name, filename)

    # Paper metadata
    paper_meta = assets.get("paper_metadata", {})
    title = paper_meta.get("title")
    authors = paper_meta.get("authors", [])
    pub_date = paper_meta.get("publication_date")
    abstract = paper_meta.get("abstract")
    doi = paper_meta.get("doi")
    journal = paper_meta.get("journal")
    meta_source = paper_meta.get("metadata_source")
    conv_backend = paper_meta.get("backend")

    if title:
        st.markdown(f"**Title:** {title}")
    if authors:
        st.markdown(f"**Authors:** {', '.join(authors)}")
    if journal:
        st.markdown(f"**Journal:** {journal}")
    if pub_date:
        st.markdown(f"**Published:** {pub_date}")
    if doi:
        st.markdown(f"**DOI:** [{doi}]({doi})" if doi.startswith("http") else f"**DOI:** [{doi}](https://doi.org/{doi})")
    if abstract:
        with st.expander("Abstract", expanded=False):
            st.write(abstract)
    # References section from markdown
    references = assets.get("references", "")
    if references:
        with st.expander("References", expanded=False):
            st.markdown(references)
    # Show source tags
    tags = []
    if conv_backend:
        tags.append(f"Converted with: {conv_backend}")
    if meta_source:
        tags.append(f"Metadata from: {meta_source}")
    if tags:
        st.caption(" | ".join(tags))

    tables = assets.get("tables", [])
    images = assets.get("images", [])

    if not tables and not images:
        return

    stem = filename.rsplit(".", 1)[0] if "." in filename else filename

    # Tables section
    if tables:
        st.markdown(f"**Tables ({len(tables)})**")
        for t in tables:
            caption = t.get("caption", "") or f"Table {t['index']}"
            page = t.get("page")
            page_str = f" (page {page})" if page else ""

            dl_url = f"{BACKEND_URL}/preprocess/assets/{dir_name}/{filename}/tables/{t['file']}"
            table_data = None
            try:
                table_resp = httpx.get(dl_url, timeout=10.0)
                if table_resp.status_code == 200:
                    table_data = table_resp.content
            except Exception:
                pass

            show_key = f"show_table_{filename}_{t['index']}"
            analyze_key = f"analyze_table_{filename}_{t['index']}"
            col_label, col_toggle, col_analyze, col_dl = st.columns([4, 0.7, 1, 1])
            with col_label:
                st.write(f"- {caption}{page_str}")
            with col_toggle:
                if table_data and t["file"].endswith(".csv"):
                    st.checkbox("Show", key=show_key, value=False)
            with col_analyze:
                if table_data and t["file"].endswith(".csv"):
                    if st.button("Analyze", key=f"btn_{analyze_key}", type="secondary"):
                        st.session_state[analyze_key] = True
            with col_dl:
                if table_data:
                    mime = "text/csv" if t["file"].endswith(".csv") else "text/markdown"
                    st.download_button(
                        label="Download",
                        data=table_data,
                        file_name=t["file"],
                        mime=mime,
                        key=f"dl_table_{filename}_{t['index']}",
                    )

            # Show dataframe if toggled on
            if st.session_state.get(show_key) and table_data and t["file"].endswith(".csv"):
                import pandas as pd
                from io import StringIO
                df = pd.read_csv(StringIO(table_data.decode("utf-8")))
                st.dataframe(df, use_container_width=True)

            # Analyze table with LLM
            if st.session_state.get(analyze_key) and t["file"].endswith(".csv"):
                with st.spinner("Analyzing table..."):
                    try:
                        resp = httpx.post(
                            f"{BACKEND_URL}/preprocess/analyze-table",
                            json={"dir_name": dir_name, "filename": filename, "table_file": t["file"]},
                            timeout=120.0,
                        )
                        resp.raise_for_status()
                        analysis = resp.json().get("analysis", "")
                        st.info(analysis)
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
                st.session_state[analyze_key] = False

    # Images section
    if images:
        st.markdown(f"**Images ({len(images)})**")
        for img in images:
            caption = img.get("caption", "") or f"Image {img['index']}"
            page = img.get("page")
            page_str = f" (p.{page})" if page else ""

            dl_url = f"{BACKEND_URL}/preprocess/assets/{dir_name}/{filename}/images/{img['file']}"
            img_data = None
            try:
                img_resp = httpx.get(dl_url, timeout=10.0)
                if img_resp.status_code == 200:
                    img_data = img_resp.content
            except Exception:
                pass

            show_key = f"show_img_{filename}_{img['index']}"
            col_label, col_toggle, col_dl = st.columns([4, 1, 1])
            with col_label:
                st.write(f"- {caption}{page_str}")
            with col_toggle:
                if img_data:
                    st.checkbox("Show", key=show_key, value=False)
            with col_dl:
                if img_data:
                    st.download_button(
                        label="Download",
                        data=img_data,
                        file_name=img["file"],
                        mime="image/png",
                        key=f"dl_img_{filename}_{img['index']}",
                    )

            # Show image thumbnail if toggled on
            if st.session_state.get(show_key) and img_data:
                from io import BytesIO
                from PIL import Image as PILImage
                pil_img = PILImage.open(BytesIO(img_data))
                orig_w, orig_h = pil_img.size
                if orig_h > 200:
                    thumb_h = 200
                    thumb_w = int(orig_w * thumb_h / orig_h)
                    display_img = pil_img.resize((thumb_w, thumb_h))
                else:
                    display_img = pil_img
                st.image(display_img, caption=f"{caption}{page_str} ({orig_w}x{orig_h})")


def _preprocess_single_file(dir_name: str, filename: str, backend: str = "docling", metadata_backend: str = "openalex"):
    """Call backend to convert a single PDF. Returns True on success."""
    try:
        resp = httpx.post(
            f"{BACKEND_URL}/preprocess/convert",
            json={"dir_name": dir_name, "filename": filename, "backend": backend, "metadata_backend": metadata_backend},
            timeout=300.0,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Error converting {filename}: {e}")
        return False




def render_preprocessing_tab():
    st.subheader("PDF Management")
    st.write("Convert PDFs to markdown. Place PDF directories in the `data/pdf_input/` folder.")

    backend = st.session_state.get("preprocess_backend", "pymupdf")
    metadata_backend = st.session_state.get("metadata_backend", "openalex")

    # Handle enrich-metadata action
    if "enrich_action" in st.session_state:
        action = st.session_state.pop("enrich_action")
        meta_labels = {"openalex": "OpenAlex", "crossref": "CrossRef", "semantic_scholar": "Semantic Scholar"}
        be_label = meta_labels.get(action["backend"], action["backend"])
        with st.status(f"Fetching metadata from {be_label}...", expanded=True) as status:
            t0 = time.monotonic()
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/preprocess/enrich-metadata",
                    json={"dir_name": action["dir_name"], "filename": action["filename"], "backend": action["backend"]},
                    timeout=30.0,
                )
                resp.raise_for_status()
                result = resp.json()
                elapsed = time.monotonic() - t0
                if result.get("enriched"):
                    status.update(label=f"Metadata enriched for {action['filename']} via {be_label} ({elapsed:.1f}s)", state="complete", expanded=False)
                else:
                    status.update(label=f"No metadata found for {action['filename']} on {be_label} ({elapsed:.1f}s)", state="error", expanded=True)
            except Exception as e:
                elapsed = time.monotonic() - t0
                st.error(f"Error enriching metadata: {e}")
                status.update(label=f"Failed ({elapsed:.1f}s)", state="error", expanded=True)

    # Handle pending single-file actions from previous render
    if "preprocess_action" in st.session_state:
        action = st.session_state.pop("preprocess_action")
        if action["type"] == "convert":
            be = action.get("backend", backend)
            be_label = "PyMuPDF" if be == "pymupdf" else "Docling"
            with st.status(f"Converting {action['filename']} ({be_label})...", expanded=True) as status:
                st.write(f"Converting PDF to markdown with {be_label}...")
                t0 = time.monotonic()
                meta_be = action.get("metadata_backend", metadata_backend)
                if _preprocess_single_file(action["dir_name"], action["filename"], backend=be, metadata_backend=meta_be):
                    elapsed = time.monotonic() - t0
                    status.update(label=f"Converted {action['filename']} in {elapsed:.1f}s", state="complete", expanded=False)
                else:
                    elapsed = time.monotonic() - t0
                    status.update(label=f"Failed to convert {action['filename']} ({elapsed:.1f}s)", state="error", expanded=True)
        elif action["type"] == "delete":
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/preprocess/delete",
                    json={"dir_name": action["dir_name"], "filename": action["filename"]},
                    timeout=10.0,
                )
                resp.raise_for_status()
                st.toast(f"Deleted preprocessed output for {action['filename']}")
            except Exception as e:
                st.error(f"Error deleting: {e}")

    # Handle re-process: convert right after delete
    if "preprocess_reconvert" in st.session_state:
        reconvert = st.session_state.pop("preprocess_reconvert")
        re_be = reconvert.get("backend", backend)
        re_label = "PyMuPDF" if re_be == "pymupdf" else "Docling"
        with st.status(f"Re-processing {reconvert['filename']} ({re_label})...", expanded=True) as status:
            st.write(f"Deleting old output and re-extracting with {re_label}...")
            t0 = time.monotonic()
            if _preprocess_single_file(reconvert["dir_name"], reconvert["filename"], backend=re_be, metadata_backend=metadata_backend):
                elapsed = time.monotonic() - t0
                status.update(label=f"Re-processed {reconvert['filename']} in {elapsed:.1f}s", state="complete", expanded=False)
            else:
                elapsed = time.monotonic() - t0
                status.update(label=f"Failed to re-process {reconvert['filename']} ({elapsed:.1f}s)", state="error", expanded=True)

    # Fetch available directories
    try:
        response = httpx.get(f"{BACKEND_URL}/preprocess/directories", timeout=5.0)
        response.raise_for_status()
        directories = response.json()
    except Exception as e:
        st.error(f"Error fetching directories: {e}")
        return

    if not directories:
        st.info("No directories found in `data/pdf_input/`. Place a folder with PDFs there to get started.")
        return

    # Directory selector
    dir_names = [d["name"] for d in directories]
    dir_info = {d["name"]: d for d in directories}
    selected_dir = st.selectbox(
        "Select directory",
        options=dir_names,
        format_func=lambda n: f"{n} ({dir_info[n]['pdf_count']} PDFs)",
    )

    if not selected_dir:
        return

    # Scan selected directory
    try:
        scan_response = httpx.post(
            f"{BACKEND_URL}/preprocess/scan",
            json={"dir_name": selected_dir},
            timeout=10.0,
        )
        scan_response.raise_for_status()
        scan_data = scan_response.json()
    except Exception as e:
        st.error(f"Error scanning directory: {e}")
        return

    files = scan_data["files"]
    pending = [f for f in files if not f["processed"]]
    processed = [f for f in files if f["processed"]]

    st.write(f"**{len(processed)}/{len(files)}** processed, **{len(pending)}** pending")

    # "Convert All" button — processes pending files one by one
    if pending:
        if st.button("Convert All", type="primary", use_container_width=True):
            total = len(pending)
            with st.status(f"Converting {total} PDFs...", expanded=True) as status:
                progress_bar = st.progress(0)
                success_count = 0
                error_count = 0
                t0 = time.monotonic()
                for i, f in enumerate(pending):
                    fname = f["filename"]
                    status.update(label=f"Converting {i+1}/{total} — {fname}")
                    if _preprocess_single_file(selected_dir, fname, backend=backend, metadata_backend=metadata_backend):
                        success_count += 1
                        elapsed = time.monotonic() - t0
                        st.write(f"Converted `{fname}` ({elapsed:.1f}s)")
                    else:
                        error_count += 1
                    progress_bar.progress((i + 1) / total)

                elapsed = time.monotonic() - t0
                if error_count == 0:
                    status.update(label=f"Done — converted {success_count}/{total} files in {elapsed:.1f}s", state="complete", expanded=False)
                else:
                    status.update(label=f"Done — {success_count} converted, {error_count} failed in {elapsed:.1f}s", state="error", expanded=True)
            st.rerun()
    else:
        st.success("All files in this directory have been preprocessed.")

    st.divider()

    # File list with per-file actions
    for f in files:
        fname = f["filename"]
        is_done = f["processed"]

        if is_done:
            # Peek at metadata for a richer expander label
            _assets = _fetch_pdf_assets(selected_dir, fname)
            _pm = _assets.get("paper_metadata", {})
            _label_title = _pm.get("title")
            _expander_label = f"`{fname}` — {_label_title}" if _label_title else f"`{fname}` — **done**"

            with st.expander(_expander_label):
                stem = fname.rsplit(".", 1)[0] if "." in fname else fname

                # Action buttons — "Get Metadata" only when auto-enrich is disabled (None)
                _meta_be = st.session_state.get("metadata_backend", "openalex")

                if _meta_be == "none":
                    col_meta, col_dl_md, col_dl_json, col_reprocess, col_delete = st.columns([1.2, 1, 1, 1, 1])
                else:
                    col_dl_md, col_dl_json, col_reprocess, col_delete = st.columns([1, 1, 1, 1])
                    col_meta = None

                if col_meta is not None:
                    with col_meta:
                        if st.button("Get Metadata", key=f"enrich_{fname}", type="secondary"):
                            st.session_state["enrich_action"] = {
                                "dir_name": selected_dir,
                                "filename": fname,
                                "backend": "openalex",
                            }
                            st.rerun()
                with col_dl_md:
                    try:
                        md_resp = httpx.get(f"{BACKEND_URL}/preprocess/download/{selected_dir}/{fname}/markdown", timeout=10.0)
                        if md_resp.status_code == 200:
                            st.download_button("Download .md", data=md_resp.content, file_name=f"{stem}.md", mime="text/markdown", key=f"dl_md_{fname}")
                    except Exception:
                        pass
                with col_dl_json:
                    try:
                        json_resp = httpx.get(f"{BACKEND_URL}/preprocess/download/{selected_dir}/{fname}/metadata", timeout=10.0)
                        if json_resp.status_code == 200:
                            st.download_button("Download .json", data=json_resp.content, file_name=f"{stem}_metadata.json", mime="application/json", key=f"dl_json_{fname}")
                    except Exception:
                        pass
                with col_reprocess:
                    if st.button("Re-process (Docling)", key=f"reprocess_{fname}", type="secondary"):
                        st.session_state["preprocess_action"] = {
                            "type": "delete",
                            "dir_name": selected_dir,
                            "filename": fname,
                        }
                        st.session_state["preprocess_reconvert"] = {
                            "dir_name": selected_dir,
                            "filename": fname,
                            "backend": "docling",
                        }
                        st.rerun()
                with col_delete:
                    if st.button("Delete .md", key=f"delete_{fname}", type="secondary"):
                        st.session_state["preprocess_action"] = {
                            "type": "delete",
                            "dir_name": selected_dir,
                            "filename": fname,
                        }
                        st.rerun()

                # Fetch and display assets (tables + images)
                _render_pdf_assets(selected_dir, fname)
        else:
            col_status, col_action = st.columns([5, 2])
            with col_status:
                st.write(f"`{fname}` — pending")
            with col_action:
                if st.button("Process PDF", key=f"convert_{fname}", type="primary"):
                    st.session_state["preprocess_action"] = {
                        "type": "convert",
                        "dir_name": selected_dir,
                        "filename": fname,
                        "backend": backend,
                    }
                    st.rerun()


# ---------------------------------------------------------------------------
# Tab 2: Collection Management
# ---------------------------------------------------------------------------

def _render_create_collection_section():
    """Render the create-collection form. Separated so early returns don't skip the collection list."""
    # List preprocessed subdirectories from history
    preprocessed_dirs = []
    try:
        hist_resp = httpx.get(f"{BACKEND_URL}/preprocess/history", timeout=5.0)
        hist_resp.raise_for_status()
        history = hist_resp.json()
        preprocessed_dirs = list(history.get("directories", {}).keys())
    except Exception:
        pass

    if not preprocessed_dirs:
        st.info("No preprocessed directories found. Go to the PDF Preprocessing tab first.")
        return

    selected_dir = st.selectbox(
        "Select preprocessed directory",
        options=preprocessed_dirs,
        format_func=lambda d: d,
    )

    if not selected_dir:
        return

    preprocessed_path = f"/data/preprocessed/{selected_dir}"

    # Scan the path
    scan_data = None
    try:
        scan_resp = httpx.post(
            f"{BACKEND_URL}/ingest/scan",
            json={"path": preprocessed_path},
            timeout=10.0,
        )
        if scan_resp.status_code == 404:
            st.warning("Directory not found. Check the path or preprocess PDFs in Tab 1 first.")
            return
        scan_resp.raise_for_status()
        scan_data = scan_resp.json()
    except httpx.HTTPStatusError:
        st.warning("Directory not found or not accessible.")
        return
    except Exception as e:
        st.error(f"Error scanning: {e}")
        return

    files = scan_data.get("files", [])
    total_pdfs = scan_data.get("total_pdfs", 0)
    if not files:
        st.warning(f"No preprocessed files found (0 out of {total_pdfs} PDFs). Go to the PDF Management tab first.")
        return

    col_info, col_sel_all, col_clr_all = st.columns([4, 1, 1])
    with col_info:
        st.write(f"Found **{len(files)}** preprocessed files out of **{total_pdfs}** PDFs")
    with col_sel_all:
        if st.button("Select all", key="ingest_select_all"):
            for f in files:
                st.session_state[f"ingest_sel_{f['markdown_file']}"] = True
            st.rerun()
    with col_clr_all:
        if st.button("Clear all", key="ingest_clear_all"):
            for f in files:
                st.session_state[f"ingest_sel_{f['markdown_file']}"] = False
            st.rerun()

    # File selection with checkboxes
    selected_files = []
    for f in files:
        label = f["markdown_file"]
        if not f["has_metadata"]:
            label += " (no metadata)"
        default = st.session_state.get(f"ingest_sel_{f['markdown_file']}", True)
        checked = st.checkbox(label, value=default, key=f"ingest_sel_{f['markdown_file']}")
        if checked:
            selected_files.append(f)

    if not selected_files:
        st.warning("Select at least one file to ingest.")
        return

    st.caption(f"{len(selected_files)}/{len(files)} files selected")

    st.divider()

    # Collection creation
    col_name = st.text_input("Collection name", placeholder="e.g. my_research_papers")

    # Search type selection
    search_type_label = st.radio(
        "Search type",
        ["Dense only", "Hybrid (Dense + BM42)"],
        horizontal=True,
        key="ingest_search_type",
    )
    search_type = "hybrid" if "Hybrid" in search_type_label else "dense"

    # Chunking controls
    col_mode, col_cs, col_ov = st.columns(3)
    with col_mode:
        chunk_mode = st.radio("Chunk mode", ["tokens", "characters"], horizontal=True, key="ingest_chunk_mode")

    # Track mode changes and reset defaults
    prev_mode_key = "_prev_ingest_chunk_mode"
    if prev_mode_key not in st.session_state or st.session_state[prev_mode_key] != chunk_mode:
        st.session_state[prev_mode_key] = chunk_mode
        if chunk_mode == "tokens":
            st.session_state["ingest_chunk_size"] = 500
            st.session_state["ingest_chunk_overlap"] = 100
        else:
            st.session_state["ingest_chunk_size"] = 2500
            st.session_state["ingest_chunk_overlap"] = 500

    with col_cs:
        chunk_size = st.number_input(f"Chunk size ({chunk_mode})", min_value=100, max_value=10000, step=50, key="ingest_chunk_size")
    with col_ov:
        chunk_overlap = st.number_input(f"Chunk overlap ({chunk_mode})", min_value=0, max_value=2000, step=25, key="ingest_chunk_overlap")

    if st.button("Ingest Papers into Collection", type="primary"):
        if not col_name:
            st.warning("Please enter a collection name.")
            return

        # Create collection
        total = len(selected_files)
        with st.status(f"Creating collection and ingesting {total} files...", expanded=True) as status:
            st.write("Creating Qdrant collection...")
            try:
                create_resp = httpx.post(
                    f"{BACKEND_URL}/ingest/create",
                    json={
                        "name": col_name,
                        "preprocessed_path": preprocessed_path,
                        "search_type": search_type,
                    },
                    timeout=30.0,
                )
                if create_resp.status_code == 409:
                    st.error("Collection already exists. Choose a different name.")
                    status.update(label="Failed — collection already exists", state="error")
                    return
                create_resp.raise_for_status()
                create_data = create_resp.json()
            except httpx.HTTPStatusError as e:
                st.error(f"Error creating collection: {e.response.text}")
                status.update(label="Failed to create collection", state="error")
                return
            except Exception as e:
                st.error(f"Error creating collection: {e}")
                status.update(label="Failed to create collection", state="error")
                return

            collection_id = create_data["collection_id"]

            # Ingest selected files one by one with progress
            progress_bar = st.progress(0)
            for i, f in enumerate(selected_files):
                pct = int((i / total) * 100)
                status.update(label=f"Ingesting {i+1}/{total} ({pct}%) — {f['markdown_file']}")
                st.write(f"Ingesting `{f['markdown_file']}`...")
                try:
                    ingest_resp = httpx.post(
                        f"{BACKEND_URL}/ingest/{collection_id}/file",
                        json={
                            "markdown_file": f["markdown_file"],
                            "preprocessed_path": preprocessed_path,
                            "chunk_size": chunk_size,
                            "chunk_overlap": chunk_overlap,
                            "chunk_mode": chunk_mode,
                        },
                        timeout=300.0,
                    )
                    ingest_resp.raise_for_status()
                except Exception as e:
                    st.error(f"Error ingesting {f['markdown_file']}: {e}")
                    status.update(label=f"Failed on {f['markdown_file']}", state="error")
                    break
                progress_bar.progress((i + 1) / total)
            else:
                status.update(label=f"Done — ingested {total} files into '{col_name}'", state="complete", expanded=False)
        st.rerun()


def render_collection_tab():
    st.subheader("Collection Management")
    st.write("Create a collection from preprocessed markdown files and ingest them into Qdrant.")

    # Handle pending deletion from previous render (must be before any early return)
    if "delete_collection_id" in st.session_state:
        cid = st.session_state.pop("delete_collection_id")
        try:
            resp = httpx.delete(f"{BACKEND_URL}/collections/{cid}", timeout=10.0)
            resp.raise_for_status()
            st.success("Collection deleted.")
        except Exception as e:
            st.error(f"Error deleting collection: {e}")

    # --- Create new collection section ---
    _render_create_collection_section()

    # Show existing collections
    st.divider()
    st.subheader("Existing Collections")
    collections = get_collections()
    if not collections:
        st.info("No collections yet.")
    else:
        for c in collections:
            col_a, col_b = st.columns([5, 1])
            with col_a:
                s_type = c.get("search_type", "dense")
                badge = "hybrid" if s_type == "hybrid" else "dense"
                st.write(f"**{c['name']}** (ID: `{c['collection_id']}`, {c.get('paper_count', 0)} papers, `{badge}`)")
            with col_b:
                if st.button("Delete", key=f"del_{c['collection_id']}", type="secondary"):
                    st.session_state["delete_collection_id"] = c["collection_id"]
                    st.rerun()


# ---------------------------------------------------------------------------
# Tab 3: RAG (Search + Generate)
# ---------------------------------------------------------------------------

def render_rag_tab():
    st.subheader("RAG Query")

    # Collection selector
    collections = get_collections()
    if not collections:
        st.info("No collections yet. Create one in the Collection Management tab.")
        return

    collection_names = [c["name"] for c in collections]
    collection_map = {c["name"]: c for c in collections}

    selected_name = st.selectbox("Select Collection", options=collection_names, key="rag_collection")
    if not selected_name:
        return

    selected_collection = collection_map[selected_name]
    collection_id = selected_collection["collection_id"]

    # Paper selection
    papers = get_papers(collection_id)
    if not papers:
        st.warning("No papers in this collection.")
        return

    with st.expander("Filter by papers (optional)", expanded=False):
        st.write("Leave all unchecked to query all papers.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Select All", key="rag_sel_all"):
                for p in papers:
                    st.session_state[f"rag_sel_{p['paper_id']}"] = True
                st.rerun()
        with col2:
            if st.button("Clear All", key="rag_clr_all"):
                for p in papers:
                    st.session_state[f"rag_sel_{p['paper_id']}"] = False
                st.rerun()

        selected_paper_ids = []
        for paper in papers:
            paper_id = paper["paper_id"]
            label = paper.get("title") or paper.get("filename", paper_id)
            checked = st.checkbox(label, value=st.session_state.get(f"rag_sel_{paper_id}", False), key=f"rag_sel_{paper_id}")
            if checked:
                selected_paper_ids.append(paper_id)

        if selected_paper_ids:
            st.caption(f"{len(selected_paper_ids)} paper(s) selected")
        else:
            st.caption("All papers will be queried")

    st.divider()

    query_text = st.text_area(
        "Enter your question:",
        placeholder="e.g., What are the main findings about attention mechanisms?",
        height=100,
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        top_k = st.slider("Top-K chunks", min_value=1, max_value=50, value=10)
    with col_b:
        max_tokens = st.slider("Response length (words)", min_value=50, max_value=2000, value=500, step=50)
    with col_c:
        pass  # Citations always shown

    # Hybrid search toggle
    use_hybrid = False
    if selected_collection.get("search_type") == "hybrid":
        use_hybrid = st.checkbox("Hybrid search (Dense + BM42)", value=False, key="rag_use_hybrid")
    else:
        st.checkbox("Hybrid search (Dense + BM42)", value=False, disabled=True, key="rag_use_hybrid_disabled",
                     help="This collection was created with dense-only search. Recreate with 'Hybrid' to enable.")

    if st.button("Search", type="primary", use_container_width=True):
        if not query_text:
            st.warning("Please enter a question.")
            return

        with st.spinner("Searching..."):
            result = rag_query(
                collection_id,
                query_text,
                paper_ids=selected_paper_ids if selected_paper_ids else None,
                limit=top_k,
                max_tokens=max_tokens,
                use_hybrid=use_hybrid,
            )

            if result:
                answer = result.get("answer", "")
                if answer:
                    st.markdown("### Answer")
                    st.markdown(answer)
                    st.divider()

                markdown_export = export_to_markdown("search", result, query_text)
                st.download_button(
                    label="Export to Markdown",
                    data=markdown_export,
                    file_name=f"search_results_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                )

                results = result.get("results", [])
                st.markdown(f"**Retrieved Passages ({len(results)})**")
                for i, r in enumerate(results):
                    label = f"#{i+1} (Score: {r['score']:.3f}) — {r['unique_id']}"
                    with st.expander(label):
                        st.markdown(r["chunk_text"])
                        st.caption(f"Page: {r['page_number']} | Type: {r['chunk_type']}")

                if "citations" in result and result["citations"]:
                    with st.expander(f"Citations ({len(result['citations'])})"):
                        for cite_key, citation in result["citations"].items():
                            st.markdown(f"**[{cite_key}]** {citation['title']}")
                            if citation.get("authors"):
                                st.caption(f"{', '.join(citation['authors'])} ({citation.get('year', 'N/A')})")
                            st.markdown("**APA:**")
                            st.text(citation["apa"])
                            st.markdown("**BibTeX:**")
                            st.code(citation["bibtex"], language="bibtex")
                            st.divider()


# ---------------------------------------------------------------------------
# Tab 4: Explore Paper
# ---------------------------------------------------------------------------

def render_explore_tab():
    st.subheader("Explore Paper")

    collections = get_collections()
    if not collections:
        st.info("No collections yet. Create one in the Collection Management tab.")
        return

    collection_names = [c["name"] for c in collections]
    collection_map = {c["name"]: c["collection_id"] for c in collections}

    selected_name = st.selectbox("Select Collection", options=collection_names, key="explore_collection")
    if not selected_name:
        return

    collection_id = collection_map[selected_name]

    papers = get_papers(collection_id)
    if not papers:
        st.warning("No papers in this collection.")
        return

    # Single paper selector
    paper_labels = []
    paper_map = {}
    for p in papers:
        label = p.get("title") or p.get("filename", p["paper_id"])
        paper_labels.append(label)
        paper_map[label] = p

    selected_label = st.selectbox("Select a paper to explore", options=paper_labels, key="explore_paper")
    if not selected_label:
        return

    selected_paper = paper_map[selected_label]
    selected_paper_id = selected_paper["paper_id"]

    # Reset chat history when paper changes
    if st.session_state.get("explore_current_paper") != selected_paper_id:
        st.session_state["explore_current_paper"] = selected_paper_id
        st.session_state["explore_chat_history"] = []

    # --- Paper metadata from collection (confirms Qdrant knows it) ---
    paper_detail = get_paper_detail(collection_id, selected_paper_id)
    if paper_detail:
        title = paper_detail.get("title") or selected_paper_id
        authors = paper_detail.get("authors", [])
        source_pdf = paper_detail.get("source_pdf") or selected_paper.get("filename", "")
        journal = paper_detail.get("journal")
        pub_date = paper_detail.get("publication_date")
        doi = paper_detail.get("doi")
        abstract = paper_detail.get("abstract")
        meta_source = paper_detail.get("metadata_source")
        chunks_created = paper_detail.get("chunks_created")
        unique_id = paper_detail.get("unique_id")

        st.markdown(f"**{title}**")
        if authors:
            st.markdown(f"*{', '.join(authors)}*")
        detail_parts = []
        if journal:
            detail_parts.append(f"**Journal:** {journal}")
        if pub_date:
            detail_parts.append(f"**Published:** {pub_date}")
        if doi:
            doi_link = doi if doi.startswith("http") else f"https://doi.org/{doi}"
            detail_parts.append(f"**DOI:** [{doi}]({doi_link})")
        if detail_parts:
            st.markdown(" | ".join(detail_parts))
        if abstract:
            with st.expander("Abstract", expanded=False):
                st.write(abstract)
        # Collection-specific info
        tags = []
        if unique_id:
            tags.append(f"ID: {unique_id}")
        if chunks_created:
            tags.append(f"Chunks: {chunks_created}")
        if meta_source:
            tags.append(f"Metadata: {meta_source}")
        if tags:
            st.caption(" | ".join(tags))
    else:
        title = selected_paper.get("title") or selected_paper_id
        source_pdf = selected_paper.get("source_pdf") or selected_paper.get("filename", "")
        st.markdown(f"**{title}**")
        st.caption("Full metadata not available in collection.")

    # --- Paper References ---
    references_text = paper_detail.get("references", "") if paper_detail else ""
    if references_text:
        with st.expander("Show Paper References", expanded=False):
            st.markdown(references_text)

    # --- Extract Tables & Images ---
    dir_name = paper_detail.get("preprocessed_dir") if paper_detail else selected_paper.get("preprocessed_dir")
    if dir_name and source_pdf:
        assets = _fetch_pdf_assets(dir_name, source_pdf)
        tables = assets.get("tables", [])
        images = assets.get("images", [])

        if not tables and not images:
            if st.button("Extract Tables & Images", key="explore_extract_assets", type="secondary"):
                with st.status(f"Extracting tables & images...", expanded=True) as status:
                    st.write("Re-running Docling to extract tables and images...")
                    t0 = time.monotonic()
                    try:
                        resp = httpx.post(
                            f"{BACKEND_URL}/preprocess/extract-assets",
                            json={"dir_name": dir_name, "filename": source_pdf},
                            timeout=300.0,
                        )
                        resp.raise_for_status()
                        result = resp.json()
                        elapsed = time.monotonic() - t0
                        status.update(
                            label=f"Extracted {result.get('table_count', 0)} tables, {result.get('image_count', 0)} images in {elapsed:.1f}s",
                            state="complete",
                            expanded=False,
                        )
                    except Exception as e:
                        elapsed = time.monotonic() - t0
                        st.error(f"Error extracting assets: {e}")
                        status.update(label=f"Failed ({elapsed:.1f}s)", state="error", expanded=True)
                st.rerun()
        else:
            with st.expander(f"Tables ({len(tables)}) & Images ({len(images)})", expanded=False):
                _render_assets_inline(dir_name, source_pdf, tables, images)

    st.divider()

    # --- Chat interface ---
    # Initialize chat history in session state
    if "explore_chat_history" not in st.session_state:
        st.session_state["explore_chat_history"] = []

    chat_history = st.session_state["explore_chat_history"]

    # Display existing chat messages
    for msg in chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask a question about this paper...", key="explore_chat_input"):
        # Add user message
        chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = rag_query(
                    collection_id=collection_id,
                    query_text=prompt,
                    paper_ids=[selected_paper_id],
                    limit=10,
                    max_tokens=500,
                )
                if result and result.get("answer"):
                    answer = result["answer"]
                else:
                    answer = "I couldn't find relevant information in this paper to answer your question."
                st.markdown(answer)

        # Add assistant message
        chat_history.append({"role": "assistant", "content": answer})

        # Keep only last 3 turns (6 messages)
        if len(chat_history) > 6:
            st.session_state["explore_chat_history"] = chat_history[-6:]


def _render_assets_inline(dir_name: str, filename: str, tables: list, images: list):
    """Render tables and images inline (used in explore tab)."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename

    if tables:
        st.markdown(f"**Tables ({len(tables)})**")
        for t in tables:
            caption = t.get("caption", "") or f"Table {t['index']}"
            page = t.get("page")
            page_str = f" (page {page})" if page else ""

            dl_url = f"{BACKEND_URL}/preprocess/assets/{dir_name}/{filename}/tables/{t['file']}"
            table_data = None
            try:
                table_resp = httpx.get(dl_url, timeout=10.0)
                if table_resp.status_code == 200:
                    table_data = table_resp.content
            except Exception:
                pass

            show_key = f"explore_show_table_{filename}_{t['index']}"
            analyze_key = f"explore_analyze_table_{filename}_{t['index']}"
            col_label, col_toggle, col_analyze, col_dl = st.columns([4, 0.7, 1, 1])
            with col_label:
                st.write(f"- {caption}{page_str}")
            with col_toggle:
                if table_data and t["file"].endswith(".csv"):
                    st.checkbox("Show", key=show_key, value=False)
            with col_analyze:
                if table_data and t["file"].endswith(".csv"):
                    if st.button("Analyze", key=f"btn_{analyze_key}", type="secondary"):
                        st.session_state[analyze_key] = True
            with col_dl:
                if table_data:
                    mime = "text/csv" if t["file"].endswith(".csv") else "text/markdown"
                    st.download_button(
                        label="Download",
                        data=table_data,
                        file_name=t["file"],
                        mime=mime,
                        key=f"explore_dl_table_{filename}_{t['index']}",
                    )

            if st.session_state.get(show_key) and table_data and t["file"].endswith(".csv"):
                import pandas as pd
                from io import StringIO
                df = pd.read_csv(StringIO(table_data.decode("utf-8")))
                st.dataframe(df, use_container_width=True)

            # Analyze table with LLM
            if st.session_state.get(analyze_key) and t["file"].endswith(".csv"):
                with st.spinner("Analyzing table..."):
                    try:
                        resp = httpx.post(
                            f"{BACKEND_URL}/preprocess/analyze-table",
                            json={"dir_name": dir_name, "filename": filename, "table_file": t["file"]},
                            timeout=120.0,
                        )
                        resp.raise_for_status()
                        analysis = resp.json().get("analysis", "")
                        st.info(analysis)
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
                st.session_state[analyze_key] = False

    if images:
        st.markdown(f"**Images ({len(images)})**")
        for img in images:
            caption = img.get("caption", "") or f"Image {img['index']}"
            page = img.get("page")
            page_str = f" (p.{page})" if page else ""

            dl_url = f"{BACKEND_URL}/preprocess/assets/{dir_name}/{filename}/images/{img['file']}"
            img_data = None
            try:
                img_resp = httpx.get(dl_url, timeout=10.0)
                if img_resp.status_code == 200:
                    img_data = img_resp.content
            except Exception:
                pass

            show_key = f"explore_show_img_{filename}_{img['index']}"
            col_label, col_toggle, col_dl = st.columns([4, 1, 1])
            with col_label:
                st.write(f"- {caption}{page_str}")
            with col_toggle:
                if img_data:
                    st.checkbox("Show", key=show_key, value=False)
            with col_dl:
                if img_data:
                    st.download_button(
                        label="Download",
                        data=img_data,
                        file_name=img["file"],
                        mime="image/png",
                        key=f"explore_dl_img_{filename}_{img['index']}",
                    )

            if st.session_state.get(show_key) and img_data:
                from io import BytesIO
                from PIL import Image as PILImage
                pil_img = PILImage.open(BytesIO(img_data))
                orig_w, orig_h = pil_img.size
                if orig_h > 200:
                    thumb_h = 200
                    thumb_w = int(orig_w * thumb_h / orig_h)
                    display_img = pil_img.resize((thumb_w, thumb_h))
                else:
                    display_img = pil_img
                st.image(display_img, caption=f"{caption}{page_str} ({orig_w}x{orig_h})")


# ---------------------------------------------------------------------------
# Tab 5: Compare
# ---------------------------------------------------------------------------

def render_compare_tab():
    st.subheader("Compare Papers")

    collections = get_collections()
    if not collections:
        st.info("No collections yet. Create one in the Collection Management tab.")
        return

    collection_names = [c["name"] for c in collections]
    collection_map = {c["name"]: c["collection_id"] for c in collections}

    selected_name = st.selectbox("Select Collection", options=collection_names, key="compare_collection")
    if not selected_name:
        return

    collection_id = collection_map[selected_name]

    papers = get_papers(collection_id)
    if not papers:
        st.warning("No papers in this collection.")
        return

    st.write("Select papers to compare (at least 2):")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Select All", key="compare_sel_all"):
            for p in papers:
                st.session_state[f"compare_sel_{p['paper_id']}"] = True
            st.rerun()
    with col2:
        if st.button("Clear All", key="compare_clr_all"):
            for p in papers:
                st.session_state[f"compare_sel_{p['paper_id']}"] = False
            st.rerun()

    selected_paper_ids = []
    for paper in papers:
        paper_id = paper["paper_id"]
        label = paper.get("title") or paper.get("filename", paper_id)
        checked = st.checkbox(label, value=st.session_state.get(f"compare_sel_{paper_id}", False), key=f"compare_sel_{paper_id}")
        if checked:
            selected_paper_ids.append(paper_id)

    st.caption(f"{len(selected_paper_ids)} paper(s) selected")

    st.divider()

    max_tokens = st.slider("Response length (approx. words)", min_value=50, max_value=2000, value=500, step=50, key="compare_max_tokens")

    if st.button("Compare", type="primary", use_container_width=True):
        if len(selected_paper_ids) < 2:
            st.warning("Please select at least 2 papers to compare.")
            return

        with st.spinner("Generating comparison..."):
            result = compare_papers(collection_id, selected_paper_ids, max_tokens=max_tokens)

            if result:
                markdown_export = export_to_markdown("comparison", result)
                st.download_button(
                    label="Export Comparison to Markdown",
                    data=markdown_export,
                    file_name=f"comparison_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                )

                st.markdown("### Comparison")
                st.markdown(result["comparison"])

                st.divider()
                st.markdown("### Papers Compared")
                for paper in result.get("papers", []):
                    st.write(f"- **{paper['title']}** ({paper.get('year', 'N/A')}) - {', '.join(paper['authors'])}")


# ---------------------------------------------------------------------------
# Sidebar: Settings
# ---------------------------------------------------------------------------

def render_settings_sidebar():
    with st.sidebar:
        st.header("Settings")

        # Fetch current settings
        current = {}
        try:
            resp = httpx.get(f"{BACKEND_URL}/settings", timeout=5.0)
            resp.raise_for_status()
            current = resp.json()
        except Exception:
            st.error("Could not load settings from backend.")
            return

        # Fetch available Ollama models
        ollama_models = []
        try:
            resp = httpx.get(f"{BACKEND_URL}/ollama/models", timeout=10.0)
            resp.raise_for_status()
            ollama_models = [m["name"] for m in resp.json()]
        except Exception:
            st.warning("Could not fetch Ollama models.")

        def _find_model_index(options: list, current_value: str) -> int:
            """Find index matching current_value, handling missing :latest tag."""
            if current_value in options:
                return options.index(current_value)
            # Try matching with/without :latest
            for i, opt in enumerate(options):
                bare = opt.split(":")[0]
                if bare == current_value or bare == current_value.split(":")[0]:
                    return i
            return 0

        # Embedding model
        cur_embed = current.get("embedding_model", "")
        embed_options = ollama_models if ollama_models else [cur_embed]
        embedding_model = st.selectbox("Embedding model", options=embed_options, index=_find_model_index(embed_options, cur_embed))

        # LLM model
        cur_llm = current.get("llm_model", "")
        llm_options = ollama_models if ollama_models else [cur_llm]
        llm_model = st.selectbox("Generation model (LLM)", options=llm_options, index=_find_model_index(llm_options, cur_llm))

        st.divider()

        # PDF conversion backend
        st.radio(
            "PDF conversion backend",
            options=["pymupdf", "docling"],
            format_func=lambda b: "Basic (PyMuPDF) — fast" if b == "pymupdf" else "Docling — thorough, scanned PDFs",
            key="preprocess_backend",
        )

        # Metadata API backend
        _meta_labels = {
            "openalex": "OpenAlex",
            "crossref": "CrossRef",
            "semantic_scholar": "Semantic Scholar",
            "none": "None",
        }
        st.radio(
            "Metadata API",
            options=["openalex", "crossref", "semantic_scholar", "none"],
            format_func=lambda b: _meta_labels[b],
            key="metadata_backend",
        )

        st.divider()

        # Directories
        pdf_input_dir = st.text_input("PDF input directory", value=current.get("pdf_input_dir", "/data/pdf_input"))

        st.divider()

        # Save button
        if st.button("Save Settings", type="primary", use_container_width=True):
            payload = {
                "embedding_model": embedding_model,
                "llm_model": llm_model,
                "pdf_input_dir": pdf_input_dir,
                "preprocessed_dir": "/data/preprocessed",
            }
            try:
                save_resp = httpx.post(
                    f"{BACKEND_URL}/settings",
                    json=payload,
                    timeout=10.0,
                )
                save_resp.raise_for_status()
                st.success("Settings saved!")
            except Exception as e:
                st.error(f"Error saving settings: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="PRAG-v2",
        page_icon="📚",
        layout="wide"
    )

    st.title("PRAG-v2")
    st.caption("RAG System for Academic Research Papers")

    # Check backend health
    health = check_backend_health()
    if "error" in health:
        st.error(f"Backend not available: {health['error']}")
        st.stop()

    # Sidebar settings
    render_settings_sidebar()

    # Five tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["PDF Management", "Collection Management", "RAG", "Explore Paper", "Compare"])

    with tab1:
        render_preprocessing_tab()

    with tab2:
        render_collection_tab()

    with tab3:
        render_rag_tab()

    with tab4:
        render_explore_tab()

    with tab5:
        render_compare_tab()


if __name__ == "__main__":
    main()
