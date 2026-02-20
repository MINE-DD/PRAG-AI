import streamlit as st

from helpers import check_backend_health
from sidebar import render_settings_sidebar
from tab_preprocessing import render_preprocessing_tab
from tab_collections import render_collection_tab
from tab_rag import render_rag_tab
from tab_explore import render_explore_tab
from tab_compare import render_compare_tab


def main():
    st.set_page_config(
        page_title="PRAG-v2",
        page_icon="\U0001f4da",
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
