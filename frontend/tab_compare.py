import streamlit as st

from helpers import get_collections, get_papers, compare_papers, export_to_markdown


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
