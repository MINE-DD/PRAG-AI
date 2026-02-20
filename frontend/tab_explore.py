import time

import streamlit as st
import httpx

from helpers import BACKEND_URL, get_collections, get_papers, get_paper_detail, rag_query, summarize_papers


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
                with st.status("Extracting tables & images...", expanded=True) as status:
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

    # --- Summarize button ---
    summary_key = f"explore_summary_{selected_paper_id}"
    if st.button("Summarize Paper", key="explore_summarize_btn", type="secondary"):
        with st.spinner("Generating summary..."):
            result = summarize_papers(collection_id, [selected_paper_id], max_tokens=500)
            if result and result.get("summary"):
                st.session_state[summary_key] = result["summary"]
            else:
                st.warning("Could not generate a summary for this paper.")

    if summary_key in st.session_state:
        with st.expander("Paper Summary", expanded=True):
            st.markdown(st.session_state[summary_key])

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
