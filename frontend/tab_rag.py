import streamlit as st

from helpers import get_collections, get_papers, rag_query, export_to_markdown


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

    col_a, col_b = st.columns(2)
    with col_a:
        top_k = st.slider("Top-K chunks", min_value=1, max_value=50, value=10)
    with col_b:
        max_tokens = st.slider("Response length (words)", min_value=50, max_value=2000, value=500, step=50)

    # Auto-detect hybrid from collection
    use_hybrid = selected_collection.get("search_type") == "hybrid"

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
