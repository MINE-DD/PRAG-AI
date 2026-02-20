import streamlit as st
import httpx

from helpers import BACKEND_URL, get_collections


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
