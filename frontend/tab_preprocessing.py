import time

import streamlit as st
import httpx

from helpers import BACKEND_URL


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
        elif action["type"] == "delete_pdf":
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/preprocess/delete-pdf",
                    json={"dir_name": action["dir_name"], "filename": action["filename"]},
                    timeout=10.0,
                )
                resp.raise_for_status()
                st.toast(f"Deleted {action['filename']}")
            except Exception as e:
                st.error(f"Error deleting PDF: {e}")

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

    # --- Upload PDFs section ---
    if "upload_counter" not in st.session_state:
        st.session_state["upload_counter"] = 0

    with st.expander("Upload PDFs", icon="\U0001f4c2"):
        upload_dir_name = st.text_input("Directory name", placeholder="e.g. my_papers", key="upload_dir_name")
        uploaded_files = st.file_uploader(
            "Select PDF files (you can select an entire folder's contents)",
            type=["pdf"],
            accept_multiple_files=True,
            key=f"pdf_uploader_{st.session_state['upload_counter']}",
        )
        if uploaded_files and upload_dir_name:
            if st.button("Upload", type="primary", key="do_upload"):
                with st.spinner(f"Uploading {len(uploaded_files)} file(s)..."):
                    try:
                        files_payload = [
                            ("files", (f.name, f.getvalue(), "application/pdf"))
                            for f in uploaded_files
                        ]
                        resp = httpx.post(
                            f"{BACKEND_URL}/preprocess/upload",
                            data={"dir_name": upload_dir_name},
                            files=files_payload,
                            timeout=120.0,
                        )
                        resp.raise_for_status()
                        result = resp.json()
                        st.session_state["upload_counter"] += 1
                        st.success(f"Uploaded {result['uploaded']} PDF(s) to `{result['dir_name']}`")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Upload failed: {e}")
        elif uploaded_files and not upload_dir_name:
            st.warning("Enter a directory name before uploading.")

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
            col_status, col_action, col_del = st.columns([5, 2, 1])
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
            with col_del:
                if st.button("Delete PDF", key=f"delpdf_{fname}", type="secondary"):
                    st.session_state["preprocess_action"] = {
                        "type": "delete_pdf",
                        "dir_name": selected_dir,
                        "filename": fname,
                    }
                    st.rerun()
