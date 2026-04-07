# PRAG Architecture

PRAG is a **Retrieval-Augmented Generation (RAG)** system for academic research papers.
You upload PDFs, organize them into collections, and use local or cloud LLMs to query,
summarize, and compare papers — all through a Streamlit frontend backed by a FastAPI service.

The system is organized in three layers:

- **Dependencies** — external tools and services PRAG relies on
- **API** — HTTP endpoints the frontend (and any external tool) calls
- **Services** — internal logic: PDF conversion, embeddings, chunking, LLM calls, and more

---

## System Overview

```mermaid
flowchart TB

    subgraph DEPS["PRAG Dependencies"]
        direction LR
        Docling["Docling\nPDF → Markdown"]
        PyMuPDF["PyMuPDF4LLM\nFast PDF extract"]
        MetaAPIs["OpenAlex · CrossRef\nSemantic Scholar"]
        QdrantDep["Qdrant\nVector DB"]
        OllamaDep["Ollama\nLocal LLMs"]
        AnthropicDep["Anthropic\nClaude API"]
        GoogleDep["Google Gemini\nAPI"]
        DC["Docker Compose"]
        FP["FastAPI"]
        ST["Streamlit"]
    end

    subgraph API["API PRAG"]
        direction LR
        EP_pre["Preprocess\nPDF → Markdown"]
        EP_ing["Ingest\nMarkdown → Chunks"]
        EP_pap["Papers\nMetadata & Files"]
        EP_col["Collections\nCRUD"]
        EP_rag["RAG\nQuery & Answer"]
        EP_cmp["Compare\nMulti-paper"]
        EP_sum["Summarize\nSingle paper"]
        EP_pro["Prompts\nManage templates"]
        EP_pip["Pipeline\nEnd-to-end"]
        EP_zot["Zotero\nLibrary sync"]
        EP_set["Settings\nConfig"]
        EP_hlt["Health\nStatus check"]
    end

    subgraph SVC["Services PRAG"]
        direction LR
        S_pdf["PDF Converter\nDocling / PyMuPDF4LLM"]
        S_pre["Preprocessing"]
        S_pma["Paper Metadata API"]
        S_ing["Ingestion"]
        S_chu["Chunking"]
        S_met["Metadata"]
        S_col["Collection"]
        S_cit["Citation"]
        S_qdr["Qdrant"]
        S_spa["Sparse Embedding\nBM42 / FastEmbed"]
        S_oll["Ollama"]
        S_ant["Anthropic"]
        S_goo["Google"]
        S_pro["Prompt"]
        S_key["API Keys"]
        S_zot["Zotero"]
    end

    classDef blue  fill:#AEC6E8,stroke:#5B9BD5,color:#000,rx:6
    classDef green fill:#B5D5A8,stroke:#70AD47,color:#000,rx:6
    classDef pink  fill:#F4CCCC,stroke:#E06666,color:#000,rx:6

    class Docling,PyMuPDF,MetaAPIs blue
    class QdrantDep,OllamaDep,AnthropicDep,GoogleDep green
    class DC,FP,ST pink

    class EP_pre,EP_ing,EP_zot,EP_pip blue
    class EP_pap,EP_col,EP_rag,EP_cmp,EP_sum,EP_pro green
    class EP_set,EP_hlt pink

    class S_pdf,S_pre,S_pma,S_ing,S_chu,S_met blue
    class S_col,S_cit,S_qdr,S_spa green
    class S_oll,S_ant,S_goo,S_pro,S_key,S_zot pink
```

---

## API Endpoints

| Endpoint | Method(s) | Description |
|---|---|---|
| `/preprocess` | GET, POST | List directories, convert PDFs to Markdown, manage assets |
| `/ingest` | POST | Scan preprocessed files, create collections, ingest chunks into Qdrant |
| `/papers` | GET, DELETE | List papers in a collection, retrieve or remove metadata |
| `/collections` | GET, POST, DELETE | Create, list, and delete paper collections |
| `/collections/{id}/rag` | POST | Run a RAG query against a collection |
| `/collections/{id}/summarize` | POST | Summarize a single paper using retrieved context |
| `/collections/{id}/compare` | POST | Compare two or more papers side by side |
| `/prompts` | GET | List and retrieve prompt templates by task type |
| `/pipeline` | POST | Run the full preprocess → ingest pipeline in one call |
| `/zotero` | GET, POST | Browse and import papers from a Zotero library |
| `/settings` | GET, PATCH | Read and update runtime configuration (config.yaml) |
| `/health` | GET | Check that Qdrant and Ollama are reachable |

---

## Services

| Service | Responsibility |
|---|---|
| **PDF Converter** | Abstracts Docling and PyMuPDF4LLM; selects the right converter per file |
| **Preprocessing** | Orchestrates PDF → Markdown conversion, extracts tables and images |
| **Paper Metadata API** | Fetches paper metadata from OpenAlex, CrossRef, and Semantic Scholar |
| **Ingestion** | Reads Markdown files, creates chunks, generates embeddings, upserts to Qdrant |
| **Chunking** | Splits text into overlapping chunks by characters or tokens |
| **Metadata** | Reads and writes per-paper JSON metadata from the filesystem |
| **Collection** | Manages collection directories and `collection_info.json` files |
| **Citation** | Formats paper metadata as APA or BibTeX citations |
| **Qdrant** | Wraps the Qdrant client: create collections, upsert, search (dense + hybrid RRF) |
| **Sparse Embedding** | Generates BM42 sparse vectors via FastEmbed for hybrid search |
| **Ollama** | Generates dense embeddings and LLM completions via local Ollama instance |
| **Anthropic** | Calls Anthropic's Claude API as an alternative LLM backend |
| **Google** | Calls Google Gemini API as an alternative LLM backend |
| **Prompt** | Loads, validates, and renders YAML prompt templates with variable substitution |
| **API Keys** | Stores and retrieves cloud API keys (Anthropic, Google) at runtime |
| **Zotero** | Connects to the Zotero Web API to browse and import a user's library |

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
          ├─▶ Qdrant search (dense or hybrid RRF)
          ├─▶ Context assembly + citation formatting
          └─▶ LLM generation (Ollama · Anthropic · Google)
                 └─▶ Answer + sources
```
