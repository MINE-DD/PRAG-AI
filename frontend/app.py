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
            st.info("Query interface coming soon!")

    else:
        st.info("👈 Select or create a collection to get started")


if __name__ == "__main__":
    main()
