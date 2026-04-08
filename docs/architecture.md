# PRAG Architecture

PRAG is a **Retrieval-Augmented Generation (RAG)** system for academic research papers.
Upload PDFs, organize them into collections, and use local LLMs (via Ollama) to query,
summarize, and compare papers — through a Vue.js frontend backed by a FastAPI service.

The system is organized in three layers: **Dependencies** (external tools), **Services** (internal logic), and **API** (HTTP endpoints).

---

## Dependencies

External packages and services that PRAG relies on. These are installed automatically — you only need Docker to run Qdrant and Ollama locally.

- **PDF Processing**
  - **Docling** — converts PDFs to structured Markdown, preserving tables and layout
  - **PyMuPDF4LLM** — fast alternative PDF extractor for simpler documents
  - **OpenAlex / CrossRef / Semantic Scholar** — public APIs used to enrich papers with metadata (authors, year, abstract, DOI)
- **Database Management**
  - **Qdrant** — vector database that stores chunk embeddings and handles similarity search
  - **FastEmbed** — generates sparse BM42 vectors for hybrid search
- **LLM Engines**
  - **Ollama** — runs LLMs locally (embeddings + text generation); the core and default backend
  - **Anthropic** *(optional)* — cloud LLM backend using Claude models; requires an API key
  - **Google Gemini** *(optional)* — cloud LLM backend; requires an API key
- **Application**
  - **Docker Compose** — orchestrates Qdrant and Ollama containers alongside the app
  - **FastAPI** — Python web framework powering the REST API
  - **Vue.js** — lightweight JavaScript framework for the frontend; communicates with FastAPI over HTTP

> **Note on LLM backends:** Ollama is the intended default — it runs entirely locally with no API key or internet connection required. Anthropic and Google Gemini are fully optional alternatives for users who prefer cloud-hosted models.

---

## Services

Each service is a Python class in `backend/app/services/` with one clear responsibility. Services are injected into API endpoints via FastAPI dependency injection.

- **PDF Processing**
  - **PDF Converter** (`pdf_converter_base.py`) — abstract base that selects Docling or PyMuPDF4LLM per file
  - **Docling** (`docling_service.py`) — wraps Docling's `DocumentConverter` for high-fidelity PDF conversion
  - **PyMuPDF4LLM** (`pymupdf4llm_service.py`) — wraps PyMuPDF for fast, lightweight extraction
  - **Preprocessing** (`preprocessing_service.py`) — orchestrates PDF → Markdown, extracts tables and images, saves outputs to disk
  - **Paper Metadata** (`paper_metadata_api_service.py`) — queries OpenAlex, CrossRef, and Semantic Scholar to enrich paper metadata
  - **Zotero** (`zotero_service.py`) — connects to the Zotero Web API to browse and import a user's library
- **Data & Retrieval**
  - **Ingestion** (`ingestion_service.py`) — reads Markdown files, chunks text, generates embeddings, upserts to Qdrant
  - **Chunking** (`chunking_service.py`) — splits text into overlapping chunks by characters or tokens
  - **Metadata** (`metadata_service.py`) — reads and writes per-paper JSON metadata from the filesystem
  - **Collection** (`collection_service.py`) — manages collection directories and `collection_info.json` files
  - **Citation** (`citation_service.py`) — formats paper metadata as APA or BibTeX citations
  - **Qdrant** (`qdrant_service.py`) — wraps the Qdrant client: create collections, upsert, search (dense + hybrid RRF)
  - **Sparse Embedding** (`sparse_embedding_service.py`) — generates BM42 sparse vectors via FastEmbed for hybrid search
- **LLM & Prompts**
  - **Ollama** (`ollama_service.py`) — generates dense embeddings and LLM completions via local Ollama
  - **Anthropic** (`anthropic_service.py`) — calls Anthropic's Claude API as an optional LLM backend
  - **Google** (`google_service.py`) — calls Google Gemini API as an optional LLM backend
  - **Prompt** (`prompt_service.py`) — loads, validates, and renders YAML prompt templates with variable substitution
  - **API Keys** (`api_keys_service.py`) — stores and retrieves cloud API keys (Anthropic, Google) at runtime

---

## API Endpoints

HTTP endpoints served by FastAPI. Called by the Vue.js frontend, any custom application, or directly via the interactive explorer below.

- **Ingestion Pipeline**
  - **/preprocess** — list directories, convert PDFs to Markdown, manage converted assets
  - **/ingest** — scan preprocessed files, create collections, push chunks and embeddings into Qdrant
  - **/pipeline** — end-to-end shortcut: runs preprocess + ingest in a single call
  - **/zotero** — browse and import papers from a connected Zotero library
- **Collection & Papers**
  - **/collections** — create, list, get, and delete paper collections
  - **/papers** — list, retrieve, and delete paper metadata within a collection
- **AI / RAG**
  - **/rag** — run a RAG query against a collection; returns an LLM-generated answer with source citations
  - **/compare** — compare two or more papers side by side using LLM reasoning
  - **/summarize** — generate a structured summary of a single paper
  - **/prompts** — list and retrieve YAML prompt templates by task type
- **System**
  - **/settings** — read and update runtime configuration (config.yaml) without restarting
  - **/health** — check that Qdrant and Ollama are reachable; used by the frontend status indicator

---

## Interactive API Explorer

FastAPI ships with two built-in interactive documentation UIs — no extra setup needed. Start the backend and open either URL in your browser:

| UI | URL | Best for |
|---|---|---|
| **Swagger UI** | `http://localhost:8000/docs` | Try endpoints live, fill in parameters, see responses |
| **ReDoc** | `http://localhost:8000/redoc` | Clean read-only reference, easier to browse all endpoints |

Both UIs are auto-generated from the code and stay in sync as the API evolves.

---

## Data Flow

```
PDF files
   └─▶ Preprocessing (Docling / PyMuPDF4LLM)
          └─▶ Markdown + metadata JSON on disk
                 └─▶ Ingestion
                        ├─▶ Chunking
                        ├─▶ Embeddings (Ollama dense + FastEmbed sparse)
                        └─▶ Qdrant (vector storage)

Query
   └─▶ RAG / Summarize / Compare endpoint
          ├─▶ Qdrant search (dense or hybrid retrieval)
          ├─▶ Context assembly + citation formatting
          └─▶ LLM generation (Ollama · Anthropic* · Google*)
                 └─▶ Answer + sources

* optional cloud backends
```
