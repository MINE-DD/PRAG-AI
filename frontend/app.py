import streamlit as st
import httpx
import os
from typing import Optional

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


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


def create_collection(name: str, description: str = "") -> Optional[dict]:
    """Create a new collection"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/collections",
            json={"name": name, "description": description}
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            st.error(e.response.json()["detail"])
        else:
            st.error(f"Error creating collection: {e}")
        return None


def get_collection_id(collection_name: str, collections: list) -> Optional[str]:
    """Get collection ID from name"""
    for c in collections:
        if c["name"] == collection_name:
            return c["collection_id"]
    return None


def get_papers(collection_id: str) -> list:
    """Fetch papers in a collection"""
    try:
        response = httpx.get(f"{BACKEND_URL}/collections/{collection_id}/papers")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching papers: {e}")
        return []


def upload_pdf(collection_id: str, file) -> Optional[dict]:
    """Upload a PDF to a collection"""
    try:
        files = {"file": (file.name, file, "application/pdf")}
        response = httpx.post(
            f"{BACKEND_URL}/collections/{collection_id}/papers",
            files=files,
            timeout=300.0  # 5 minutes for processing
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        st.error("Upload timed out. The PDF might be too large or processing is taking too long.")
        return None
    except httpx.HTTPStatusError as e:
        st.error(f"Error uploading PDF: {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Error uploading PDF: {e}")
        return None


def query_papers(collection_id: str, query_text: str, paper_ids: list = None, include_citations: bool = False) -> Optional[dict]:
    """Query papers in a collection"""
    try:
        payload = {
            "query_text": query_text,
            "limit": 10,
            "include_citations": include_citations
        }
        if paper_ids:
            payload["paper_ids"] = paper_ids

        response = httpx.post(
            f"{BACKEND_URL}/collections/{collection_id}/query",
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error querying papers: {e}")
        return None


def summarize_papers(collection_id: str, paper_ids: list) -> Optional[dict]:
    """Summarize papers"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/collections/{collection_id}/summarize",
            json={"paper_ids": paper_ids},
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error summarizing papers: {e}")
        return None


def compare_papers(collection_id: str, paper_ids: list, aspect: str = "all") -> Optional[dict]:
    """Compare papers"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/collections/{collection_id}/compare",
            json={"paper_ids": paper_ids, "aspect": aspect},
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error comparing papers: {e}")
        return None


def main():
    st.set_page_config(
        page_title="PRAG-v2",
        page_icon="📚",
        layout="wide"
    )

    st.title("📚 PRAG-v2")
    st.caption("RAG System for Academic Research Papers")

    # Check backend health
    health = check_backend_health()
    if "error" in health:
        st.error(f"⚠️ Backend not available: {health['error']}")
        st.stop()

    # Sidebar
    with st.sidebar:
        st.header("Collections")

        # Create collection
        with st.expander("➕ Create New Collection"):
            new_name = st.text_input("Collection Name")
            new_desc = st.text_area("Description (optional)")
            if st.button("Create"):
                if new_name:
                    result = create_collection(new_name, new_desc)
                    if result:
                        st.success(f"Created: {result['name']}")
                        st.rerun()
                else:
                    st.warning("Please enter a collection name")

        # List collections
        collections = get_collections()

        if not collections:
            st.info("No collections yet. Create one to get started!")
        else:
            collection_names = [c["name"] for c in collections]
            selected = st.selectbox(
                "Select Collection",
                options=collection_names,
                key="collection_selector"
            )

            if selected:
                st.session_state.selected_collection = selected

        # Settings
        with st.expander("⚙️ Settings"):
            st.info("Settings coming soon")

    # Main area
    if "selected_collection" in st.session_state:
        collection_name = st.session_state.selected_collection
        collection_id = get_collection_id(collection_name, collections)

        if not collection_id:
            st.error("Collection not found")
            st.stop()

        st.header(f"📁 {collection_name}")

        # Tabs for different sections
        tab1, tab2 = st.tabs(["📄 Papers", "💬 Query"])

        with tab1:
            st.subheader("Upload PDF")

            # PDF Upload
            uploaded_file = st.file_uploader(
                "Choose a PDF file",
                type=["pdf"],
                help="Upload a research paper in PDF format"
            )

            if uploaded_file is not None:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.info(f"📄 {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
                with col2:
                    if st.button("Upload & Process", type="primary"):
                        with st.spinner("Processing PDF... This may take a few minutes."):
                            result = upload_pdf(collection_id, uploaded_file)
                            if result:
                                st.success("✅ PDF uploaded and processed successfully!")
                                st.json({
                                    "Title": result.get("title", "Unknown"),
                                    "Authors": ", ".join(result.get("authors", [])),
                                    "Year": result.get("year", "N/A"),
                                    "Chunks Created": result.get("chunks_created", 0),
                                    "Status": result.get("status", "unknown")
                                })
                                # Clear the file uploader
                                st.rerun()

            st.divider()

            # List Papers
            st.subheader("Papers in Collection")

            papers = get_papers(collection_id)

            if not papers:
                st.info("No papers yet. Upload a PDF to get started!")
            else:
                st.write(f"**Total papers:** {len(papers)}")

                # Display papers in a table-like format
                for i, paper in enumerate(papers):
                    with st.expander(f"📄 {paper.get('filename', paper['paper_id'])}"):
                        st.write(f"**Paper ID:** `{paper['paper_id']}`")
                        st.write(f"**Filename:** {paper.get('filename', 'N/A')}")

                        # Action buttons
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            if st.button("View Details", key=f"view_{i}"):
                                st.info("Details view coming soon")
                        with col2:
                            if st.button("Summarize", key=f"summ_{i}"):
                                st.info("Summarization coming soon")
                        with col3:
                            if st.button("Delete", key=f"del_{i}"):
                                st.warning("Delete functionality coming soon")

        with tab2:
            st.subheader("Query Papers")

            # Get papers for selection
            papers = get_papers(collection_id)

            if not papers:
                st.warning("No papers in this collection. Upload some PDFs first!")
            else:
                # Paper selection panel
                with st.expander("📚 Select Papers", expanded=True):
                    st.write("Choose which papers to query (leave empty to query all):")

                    # Select All / Clear All buttons
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Select All"):
                            st.session_state.selected_papers = [p["paper_id"] for p in papers]
                    with col2:
                        if st.button("Clear All"):
                            st.session_state.selected_papers = []

                    # Initialize session state
                    if "selected_papers" not in st.session_state:
                        st.session_state.selected_papers = []

                    # Paper checkboxes
                    for paper in papers:
                        paper_id = paper["paper_id"]
                        filename = paper.get("filename", paper_id)

                        is_selected = paper_id in st.session_state.selected_papers
                        if st.checkbox(
                            f"📄 {filename}",
                            value=is_selected,
                            key=f"select_{paper_id}"
                        ):
                            if paper_id not in st.session_state.selected_papers:
                                st.session_state.selected_papers.append(paper_id)
                        else:
                            if paper_id in st.session_state.selected_papers:
                                st.session_state.selected_papers.remove(paper_id)

                    selected_count = len(st.session_state.selected_papers)
                    if selected_count > 0:
                        st.info(f"✓ {selected_count} paper(s) selected")
                    else:
                        st.info("All papers will be queried")

                st.divider()

                # Query interface
                st.subheader("Ask a Question")

                query_text = st.text_area(
                    "Enter your question:",
                    placeholder="e.g., What are the main findings about attention mechanisms?",
                    height=100
                )

                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    include_citations = st.checkbox("Include citations", value=True)
                with col2:
                    query_mode = st.selectbox(
                        "Mode",
                        ["Search", "Summarize", "Compare"],
                        help="Search: Find relevant passages\nSummarize: Generate summary\nCompare: Compare papers"
                    )

                if st.button("🔍 Submit", type="primary", use_container_width=True):
                    if not query_text and query_mode == "Search":
                        st.warning("Please enter a question")
                    elif query_mode in ["Summarize", "Compare"] and selected_count == 0:
                        st.warning(f"{query_mode} requires at least {'1' if query_mode == 'Summarize' else '2'} paper(s) selected")
                    else:
                        with st.spinner(f"{query_mode}ing..."):
                            if query_mode == "Search":
                                # Query/search mode
                                result = query_papers(
                                    collection_id,
                                    query_text,
                                    st.session_state.selected_papers if selected_count > 0 else None,
                                    include_citations
                                )

                                if result:
                                    st.success("✅ Search complete!")

                                    # Display results
                                    results = result.get("results", [])
                                    st.write(f"**Found {len(results)} relevant passages:**")

                                    for i, r in enumerate(results):
                                        with st.container():
                                            st.markdown(f"**Result {i+1}** (Score: {r['score']:.3f})")
                                            st.markdown(f"> {r['chunk_text']}")
                                            st.caption(f"Paper: {r['unique_id']} | Page: {r['page_number']} | Type: {r['chunk_type']}")
                                            st.divider()

                                    # Display citations if included
                                    if include_citations and "citations" in result:
                                        st.subheader("📚 Citations")
                                        for paper_id, citation in result["citations"].items():
                                            with st.expander(f"{citation['unique_id']} - {citation['title']}"):
                                                st.markdown("**APA:**")
                                                st.text(citation["apa"])
                                                st.markdown("**BibTeX:**")
                                                st.code(citation["bibtex"], language="bibtex")

                            elif query_mode == "Summarize":
                                # Summarize mode
                                result = summarize_papers(
                                    collection_id,
                                    st.session_state.selected_papers
                                )

                                if result:
                                    st.success("✅ Summary generated!")
                                    st.markdown("### Summary")
                                    st.markdown(result["summary"])

                                    st.divider()
                                    st.markdown("### Papers Summarized")
                                    for paper in result.get("papers", []):
                                        st.write(f"- **{paper['title']}** ({paper['year']}) - {', '.join(paper['authors'])}")

                            elif query_mode == "Compare":
                                # Compare mode
                                if selected_count < 2:
                                    st.error("Please select at least 2 papers to compare")
                                else:
                                    result = compare_papers(
                                        collection_id,
                                        st.session_state.selected_papers
                                    )

                                    if result:
                                        st.success("✅ Comparison generated!")
                                        st.markdown("### Comparison")
                                        st.markdown(result["comparison"])

                                        st.divider()
                                        st.markdown("### Papers Compared")
                                        for paper in result.get("papers", []):
                                            st.write(f"- **{paper['title']}** ({paper['year']}) - {', '.join(paper['authors'])}")

    else:
        st.info("👈 Select or create a collection to get started")


if __name__ == "__main__":
    main()
