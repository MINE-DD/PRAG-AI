import streamlit as st
import httpx

from helpers import BACKEND_URL


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
