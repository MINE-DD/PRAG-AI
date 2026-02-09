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
        st.header(f"Collection: {st.session_state.selected_collection}")
        st.info("PDF upload and querying coming soon!")
    else:
        st.info("👈 Select or create a collection to get started")


if __name__ == "__main__":
    main()
