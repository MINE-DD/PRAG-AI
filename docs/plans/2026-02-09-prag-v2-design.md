# PRAG-v2 Design Document

**Date:** 2026-02-09
**Version:** 1.0
**Author:** Design Session

## Overview

PRAG-v2 is a local, single-user RAG (Retrieval Augmented Generation) system for querying academic research papers. It enables researchers to upload PDFs, organize them into collections, and query across papers or drill down into specific documents. The system extracts metadata, tables, and figures from papers, creates embeddings for semantic search, and provides intelligent responses with proper citations.

**Key Features:**
- Multi-collection organization (e.g., "ML Papers", "Biology Papers")
- Batch PDF upload and processing with Docling
- Two query modes: multi-paper (compare/contrast) and single-paper (summarize/extract)
- Smart paper ordering based on query relevance
- Inline citations with structured sources
- Session-based chat with markdown export
- Support for local (Ollama) and API-based LLMs (Claude, Gemini)
- Streamlit Web UI + REST API

---

## System Architecture

PRAG-v2 runs entirely via Docker Compose with five main components:

### 1. Streamlit Web UI
The primary interface where users create collections, upload/remove PDFs, switch between query modes (multi-paper or single-paper), and export chat history to markdown.

### 2. FastAPI Backend
REST API that handles collection management, PDF processing requests, and query routing. Streamlit calls this API for all operations.

### 3. PDF Processing Pipeline (Docling)
Extracts text, metadata (title, authors, abstract, citations, etc.), tables (as text), and figures (as images with captions). Chunks content and generates embeddings via Ollama.

### 4. Qdrant Vector Database
Stores embeddings and metadata for each paper. One Qdrant collection per user collection, enabling semantic search across papers or within a specific paper.

### 5. LLM Integration (Ollama + API)
- **Local**: System Ollama for embeddings (nomic-embed-text) and generation (llama3)
- **API**: Optional Claude/Gemini API support for more powerful generation
- Query processing logic routes requests appropriately

### Data Flow
1. User uploads PDF → FastAPI triggers Docling processing
2. Extract metadata, chunk text, generate embeddings
3. Store in Qdrant
4. User queries → Backend retrieves relevant chunks
5. LLM generates response with inline citations
6. Display in UI with structured sources section

---

## Data Model & Storage

### Collections
Each collection maps to:
- A Qdrant collection (embeddings + metadata)
- A file system directory (PDFs + figures)

Collections are independent - switching collections means querying a different set of papers.

### File System Structure
```
/data/
  collections/
    {collection_id}/
      pdfs/      # Original PDF files
      figures/   # Extracted figures as images
  qdrant/        # Qdrant data volume
```

### Paper Metadata Schema
Stored in Qdrant with embeddings:
- `paper_id`: Unique identifier (UUID)
- `title`, `authors`, `publication_date`
- `abstract`, `keywords`
- `journal_conference`: Publication venue
- `citations`: List of cited papers (if extractable)
- `unique_id`: Human-readable citation ID (e.g., `VaswaniAttention2017`)
- `pdf_path`: Path to original PDF
- `figures`: List of figure paths with captions

### Qdrant Document Structure
Each chunk stored as a point in Qdrant:
- `vector`: Embedding of the text chunk
- `payload`:
  - `paper_id`, `unique_id`, `title`, `authors`, `year`
  - `chunk_text`: The actual text content
  - `chunk_type`: "abstract", "body", "table", "figure_caption"
  - `page_number`: Source page in PDF
  - `metadata`: Full paper metadata

### Chunking Strategy
Configurable (default: 500 characters, 100 character overlap):
- **Abstract**: Kept as single chunk
- **Body text**: Fixed-size overlapping chunks
- **Tables**: Each table as a chunk (extracted as markdown text)
- **Figure captions**: Each caption as a chunk (linked to image file)

### Source of Truth
- **File system (pdfs/)**: Shows what papers exist
- **Qdrant**: Stores all metadata + embeddings
- On startup: Ensure every PDF has corresponding Qdrant entries

---

## PDF Processing Pipeline

When a user uploads PDF(s) through Streamlit, the following pipeline executes:

### Step 1: PDF Upload & Storage
- Save PDF to `collections/{collection_id}/pdfs/{paper_id}.pdf`
- Generate unique `paper_id` (UUID)
- Support multiple file uploads (batch processing)

### Step 2: Docling Extraction
- Extract full text content with page numbers
- Extract metadata: title, authors, publication date, abstract, keywords, citations, journal/conference
- Generate `unique_id` for citations: first chars of title + first author last name + year (e.g., `VaswaniAttention2017`)
- Extract tables as markdown/text
- Extract figures as images → save to `collections/{collection_id}/figures/{paper_id}_fig_{n}.png` with captions

### Step 3: Chunking
- Split content using configurable strategy (default: 500 characters, 100 character overlap)
- Chunk types: abstract (single chunk), body (multiple chunks), table (one per table), figure_caption (one per figure)
- Each chunk tagged with: paper_id, unique_id, chunk_type, page_number

### Step 4: Embedding Generation
- Generate embeddings for each chunk using Ollama (default: nomic-embed-text)
- Batch processing for efficiency

### Step 5: Storage in Qdrant
- Create points in Qdrant collection with vectors + payload (chunk text, metadata, paper info)
- Store full paper metadata with first chunk for easy retrieval

### Error Handling
If any step fails:
- Rollback: delete PDF file and any partial Qdrant entries
- Return error to user in UI with clear message
- Allow retry or manual removal

---

## Query Processing Logic

PRAG-v2 uses direct programmatic routing (not autonomous agent) for simplicity and predictability.

### Query Modes

**Multi-paper Mode** (2 to n papers, default = all):
- User selects subset of papers OR uses entire collection
- Operations: Query across selected papers, Compare papers, Contrast approaches

**Single-paper Mode** (exactly 1 paper):
- User selects one specific paper
- Operations: Query paper, Summarize, Extract key findings

### Processing Functions

**1. Semantic Search**
- Query Qdrant with user question → retrieve top-k relevant chunks (default: 10)
- Supports filtering by paper_ids (multi-paper or single-paper mode)
- Returns chunks with metadata: paper title, authors, year, page number, unique_id

**2. Answer Question**
- Takes retrieved chunks + user question
- LLM generates answer with inline citations: `[Source: VaswaniAttention2017, p.3]`
- Builds structured Sources section with full paper details, relevant excerpts, and page numbers

**3. Summarize Paper**
- Single-paper mode only
- Retrieves abstract + key chunks from paper
- Generates concise summary (200-300 words) covering purpose, methods, findings

**4. Extract Key Findings**
- Identifies main contributions, results, conclusions from paper(s)
- Returns structured list of findings with citations

**5. Compare Papers**
- Multi-paper mode (2+ papers)
- Retrieves key content from selected papers
- LLM compares approaches, methodologies, findings

### Query Flow
1. User asks question in Streamlit chat
2. Streamlit sends query to FastAPI with mode and paper_ids
3. Backend classifies query type and routes to appropriate function
4. Execute function → retrieve from Qdrant → LLM generates response
5. Response includes inline citations + structured Sources section
6. Return cited paper_ids for smart reordering
7. Display in Streamlit

### Session State
- Chat history maintained in Streamlit session state (browser memory)
- User can switch modes and paper selection mid-conversation
- Export to markdown at any time

---

## Web UI & User Flows (Streamlit)

### Main Layout

**Sidebar:**
- Collection selector dropdown (list of existing collections)
- "Create Collection" button
- "Upload PDF(s)" button (multi-file uploader)
- Settings expander:
  - LLM Type: [Local (Ollama) | Claude API | Gemini API]
  - If API: API Key input (masked)
  - Model selection dropdown
  - Chunk size (characters, default: 500)
  - Chunk overlap (characters, default: 100)
  - Top-K retrieval (default: 10)
- "Export Chat to Markdown" button

**Main Area:**

**Top Section:**
- Collection name, paper count

**Paper Selection Panel:**
- Searchable list of papers with checkboxes (multi-select)
- Smart ordering: Papers cited in last query appear at top (highlighted)
- Shows: title, authors, year, unique_id
- "Select All" / "Clear Selection" buttons
- Remove button per paper (⚠️ deletes from collection)
- "Reset Order" button (return to default sorting)

**Operation Mode** (dynamically changes based on selection):
- **0 papers selected**: Prompt to select papers
- **1 paper selected**: Single-paper mode
  - Buttons: [Query] [Summarize] [Extract Findings]
- **2+ papers selected**: Multi-paper mode
  - Buttons: [Query] [Compare Papers] [Contrast Approaches]

**Chat Area:**
- Streamlit chat messages
- Inline citations: `[Source: VaswaniAttention2017, p.3]`
- Structured Sources section with full paper details

**Input:**
- Query text box (enabled when papers selected)

### Key User Flows

**Flow 1: Create Collection & Upload Papers**
1. Click "Create Collection" → enter name → creates collection
2. Collection appears in dropdown (auto-selected)
3. Click "Upload PDF(s)" → multi-file uploader
4. Select multiple PDFs → processing starts (progress bars)
5. Papers appear in list as they complete processing

**Flow 2: Query Across Collection**
1. Select collection (all papers pre-selected)
2. Enter question: "What are the main attention mechanisms?"
3. Result cites 3 papers → those papers jump to top of list
4. Select just those 3 papers
5. Click "Compare Papers" → focused comparison

**Flow 3: Drill Down on Single Paper**
1. Click one paper in list (others deselect)
2. Click "Summarize" → get paper summary
3. Ask follow-up questions about that specific paper
4. Click "Extract Findings" → get key contributions

**Flow 4: Export & Continue**
1. After several queries, click "Export Chat to Markdown"
2. Download markdown file with full conversation
3. Continue querying or switch collections

---

## API Endpoints (FastAPI)

### Collection Management

**`POST /collections`**
- Create new collection
- Body: `{name, description}`
- Returns: `{collection_id, name, created_date}`
- Error: If name exists, return `409 Conflict` with message:
  ```
  Collection "ML Papers" already exists at /data/collections/ml_papers
  Please use a different name or reprocess the existing collection.
  ```

**`GET /collections`**
- List all collections
- Returns: `[{collection_id, name, paper_count, created_date}]`

**`GET /collections/{collection_id}`**
- Get collection details + paper list
- Returns: `{collection_id, name, papers: [{paper_id, unique_id, title, authors, year}]}`

**`DELETE /collections/{collection_id}`**
- Delete Qdrant collection (embeddings only)
- Keep file directory intact (PDFs and figures preserved)

**`POST /collections/{collection_id}/reprocess`**
- Scan existing PDF directory
- Delete Qdrant collection
- Reprocess all PDFs with current settings
- Useful when changing chunk size, embedding model, etc.

### Paper Management

**`POST /collections/{collection_id}/papers`**
- Upload PDF(s)
- Multipart form data (multiple files supported)
- Returns: `{paper_ids: [], processing_status: "started"}`
- Triggers async processing pipeline

**`GET /collections/{collection_id}/papers/{paper_id}`**
- Get paper metadata
- Returns: Full paper metadata including unique_id, figures, etc.

**`DELETE /collections/{collection_id}/papers/{paper_id}`**
- Remove paper from collection
- Deletes: PDF file, figures, Qdrant entries
- Returns: `{success: true}`

### Query Operations

**`POST /query`**
- General query
- Body: `{collection_id, paper_ids: [], query_text, chat_history: []}`
- Returns: `{answer, sources: [{unique_id, title, authors, year, excerpts, pages}], cited_paper_ids: []}`

**`POST /summarize`**
- Summarize paper (requires single paper_id)
- Body: `{collection_id, paper_id, chat_history: []}`
- Returns: `{summary, sources: [...]}`

**`POST /compare`**
- Compare papers (requires 2+ paper_ids)
- Body: `{collection_id, paper_ids: [], aspect: "methodology|findings|all", chat_history: []}`
- Returns: `{comparison, sources: [...]}`

**`POST /extract-findings`**
- Extract key findings
- Body: `{collection_id, paper_ids: []}`
- Returns: `{findings: [{finding, source}], sources: [...]}`

### Configuration

**`GET /config`**
- Get current settings
- Returns: `{models: {embedding, llm}, chunking: {size, overlap}, retrieval: {top_k}}`

**`PUT /config`**
- Update settings
- Body: `{models, chunking, retrieval}` (partial updates allowed)
- Returns: `{success: true, config: {...}}`

**`POST /config/api-keys`**
- Set API key (secure)
- Body: `{provider: "anthropic|google", api_key: "..."}`
- Validates key format, saves to .env file
- Returns: `{success: true}`

**`GET /config/api-keys`**
- Get masked API keys
- Returns: `{anthropic: "sk-ant-...****", google: "AIza...****"}`

### Export

**`POST /export/markdown`**
- Export chat history to markdown
- Body: `{chat_history: [], collection_name}`
- Returns: Markdown content or download URL

### Health

**`GET /health`**
- Check system health
- Returns: `{qdrant: "ok|error", ollama: "ok|error", models: {embedding: "ok", llm: "ok"}}`

---

## Deployment & Configuration

### Docker Compose Setup

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./data/qdrant:/qdrant/storage
    restart: unless-stopped

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - qdrant
    volumes:
      - ./data/collections:/data/collections
    env_file:
      - .env
    environment:
      - QDRANT_URL=http://qdrant:6333
      - OLLAMA_URL=http://host.docker.internal:11434
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Linux support
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "8501:8501"
    depends_on:
      - backend
    environment:
      - BACKEND_URL=http://backend:8000
    restart: unless-stopped
```

### Prerequisites

**System Requirements:**
1. Docker and Docker Compose installed
2. Ollama installed on host system: `https://ollama.ai`
3. At least 8GB RAM (16GB recommended for larger models)
4. 10GB+ disk space for models and data

**Setup Steps:**
1. Install and start Ollama:
   ```bash
   # Install from https://ollama.ai
   ollama serve
   ```

2. Pull required models:
   ```bash
   ollama pull nomic-embed-text
   ollama pull llama3
   ```

3. Clone PRAG-v2 and configure:
   ```bash
   git clone <repo>
   cd PRAG-v2
   cp .env.example .env
   # Edit .env to add API keys (optional)
   ```

4. Start services:
   ```bash
   docker-compose up -d
   ```

5. Access:
   - Web UI: `http://localhost:8501`
   - API docs: `http://localhost:8000/docs`

### Configuration Files

**`.env` (gitignored, chmod 600):**
```bash
# Optional API keys (securely stored)
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

# Advanced settings (optional)
QDRANT_URL=http://qdrant:6333
OLLAMA_URL=http://host.docker.internal:11434
```

**`config.yaml`:**
```yaml
models:
  embedding: "nomic-embed-text"
  llm:
    type: "local"  # or "api"
    model: "llama3"

chunking:
  size: 500      # characters
  overlap: 100   # characters
  strategy: "fixed"

retrieval:
  top_k: 10

citations:
  unique_id_format: "{author}{title_words}{year}"
```

### Data Persistence

All data stored in `./data/` directory:
- `./data/qdrant/` - Vector database
- `./data/collections/` - PDF files and figures

Backup strategy: Regular backups of `./data/` directory.

---

## Error Handling & Edge Cases

### PDF Processing Failures

**Scenario:** Docling fails to extract content (corrupted PDF, unsupported format, scanned image without OCR)

**Handling:**
- Log error with paper_id and failure reason
- Keep PDF file but mark as "processing failed" in UI
- Show error message with details
- Provide "Retry Processing" or "Remove PDF" buttons
- Allow manual metadata editing (future enhancement)

### Ollama Connection Issues

**Scenario:** System Ollama not running or model not available

**Handling:**
- Health check endpoint (`GET /health`) checks Ollama connectivity
- Backend startup validates Ollama connection
- Show clear error in UI:
  ```
  ⚠️ Ollama not running
  Please start Ollama: ollama serve
  Then restart PRAG-v2
  ```
- Gracefully fail queries with actionable error messages
- List required models if missing

### Qdrant Failures

**Scenario:** Qdrant container down or collection corrupted

**Handling:**
- Backend startup checks Qdrant connection
- If collection missing but PDFs exist, show status:
  ```
  ⚠️ Collection needs reprocessing
  PDFs found but embeddings missing.
  ```
- Provide "Reprocess Collection" button
- Health check reports Qdrant status

### Paper Removal During Processing

**Scenario:** User removes paper while it's still being processed

**Handling:**
- Cancel processing job immediately
- Clean up partial Qdrant entries
- Remove PDF file and figures
- Show confirmation: "Processing cancelled, paper removed"

### Empty/Invalid Citations

**Scenario:** Docling can't extract metadata (title, authors, year)

**Handling:**
- Generate fallback unique_id: `UnknownPaper_{paper_id[:8]}`
- Mark metadata as "Incomplete" in UI (badge/icon)
- Store whatever metadata was extractable
- Allow manual editing in future version
- Include in queries but flag in sources

### Collection Name Conflicts

**Scenario:** User creates collection with duplicate name

**Handling:**
- Reject creation with HTTP 409 Conflict
- Error message:
  ```
  Collection "ML Papers" already exists at /data/collections/ml_papers
  Please use a different name or reprocess the existing collection.
  ```
- Provide "Reprocess Collection" button in error UI
- User must explicitly choose: new name or reprocess

### Large PDFs

**Scenario:** 100+ page papers cause slow processing (5-10 minutes)

**Handling:**
- Show processing progress bar with:
  - Current step (extraction, chunking, embedding, storage)
  - Percentage complete
  - Estimated time remaining
- Process in background (async)
- Allow other operations to continue
- Set timeout (10 minutes) with clear error if exceeded
- Suggest splitting very large PDFs if processing fails

### API Key Issues

**Scenario:** Invalid API key or rate limit exceeded

**Handling:**
- Validate API key format before saving
- Test key with simple API call when set
- If query fails due to invalid key: clear error message
- If rate limited: show retry time, suggest switching to local model
- Never log or expose full API keys

### Disk Space Issues

**Scenario:** Out of disk space during PDF upload or processing

**Handling:**
- Check available disk space before upload
- Show warning if space < 1GB
- Fail gracefully with clear error
- Suggest cleaning up old collections or moving data directory

---

## External LLM Support

### Overview

PRAG-v2 supports both local models (via Ollama) and external API-based models (Claude, Gemini) for generation. Embeddings always use local Ollama (cost-effective and fast).

### Configuration

**Model Selection in Settings:**
- **LLM Type**: Dropdown
  - Local (Ollama)
  - Claude API
  - Gemini API
- **Model**: Dropdown (options depend on type)
  - Local: llama3, mixtral, qwen, etc. (installed Ollama models)
  - Claude: claude-3-5-sonnet-20241022, claude-3-opus-20240229
  - Gemini: gemini-2.0-flash-exp, gemini-1.5-pro
- **API Key**: Masked input field (only shown for API types)

### Backend Implementation

**LLM Router:**
```python
def get_llm_client(config):
    if config.llm.type == "local":
        return OllamaClient(url=OLLAMA_URL, model=config.llm.model)
    elif config.llm.type == "api" and config.llm.model.startswith("claude"):
        return AnthropicClient(api_key=get_api_key("anthropic"), model=config.llm.model)
    elif config.llm.type == "api" and config.llm.model.startswith("gemini"):
        return GoogleClient(api_key=get_api_key("google"), model=config.llm.model)
```

**Dependencies:**
- `anthropic` SDK for Claude API
- `google-generativeai` SDK for Gemini API
- Both optional (install only if using API)

### Secure API Key Storage

**Storage Method:**
- Environment variables in `.env` file (gitignored)
- File permissions: `chmod 600 .env`
- Never in config.yaml or logs

**.env file:**
```bash
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
```

**API Endpoints:**
- `POST /config/api-keys` - Set API key
  - Validates format
  - Saves to .env file
  - Never returns full key
- `GET /config/api-keys` - Get masked keys
  - Returns: `"sk-ant-...****"` (first/last chars only)

**Security Measures:**
- Keys loaded from environment at startup
- Backend never returns full keys in responses
- Keys never logged or included in error messages
- .env file explicitly gitignored
- Optional: Docker secrets support for production

### Benefits

- **Powerful models**: Use Claude/Gemini for complex queries, comparisons, summaries
- **Local fallback**: Switch to local models for privacy or offline use
- **Cost optimization**: Embeddings always local (cheaper), generation flexible
- **No architecture change**: Just conditional routing in backend

### Usage Flow

1. User enters API key in Settings
2. Backend validates and saves securely
3. User selects API model from dropdown
4. Queries use selected LLM automatically
5. Embeddings always use local Ollama
6. User can switch between local/API at any time

---

## Future Enhancements

Not in v1, but worth considering:

1. **Citation Graph Visualization**: Show relationships between papers based on citations
2. **Manual Metadata Editing**: Allow users to correct/complete paper metadata
3. **OCR Support**: Process scanned PDFs (integrate Tesseract or similar)
4. **Export Options**: PDF, LaTeX, Notion, Obsidian formats
5. **Search Filters**: Filter papers by year, author, venue, keywords
6. **Annotation Support**: Highlight and annotate papers in UI
7. **Multi-user Support**: Add authentication for shared deployments
8. **Integration with Reference Managers**: Import from Zotero, Mendeley
9. **Advanced Chunking**: Semantic chunking, sentence-window retrieval
10. **Query History**: Persistent query log across sessions

---

## Technical Decisions & Rationale

### Why Streamlit?
- Fast development for research tools
- Built-in chat, file upload, session state
- Everything in Python (easy integration with Docling, Qdrant, Ollama)
- Acceptable UX for single-user local tools

### Why System Ollama (not Docker)?
- Better GPU access
- Models shared across projects
- User likely already has Ollama installed
- One less container to manage

### Why No metadata.json?
- Avoid synchronization complexity (three sources of truth)
- Qdrant already stores all metadata
- File system shows what PDFs exist
- Simpler = fewer bugs

### Why Characters Not Tokens for Chunking?
- Simpler implementation (no tokenizer needed)
- More predictable and consistent
- Easy for users to understand and configure
- Token count varies by model anyway

### Why Direct Logic Not Autonomous Agent?
- Simpler and more predictable
- Faster (no agent decision overhead)
- Easier to debug and test
- Sufficient for focused use case

---

## Summary

PRAG-v2 provides researchers with a powerful, local RAG system for academic papers. Key strengths:

- **Flexible querying**: Multi-paper comparisons or single-paper deep dives
- **Smart UX**: Papers cited in queries rise to the top for easy follow-up
- **Proper citations**: Inline references with structured sources
- **Privacy-first**: Runs locally, optional API support
- **Simple deployment**: Docker Compose + system Ollama
- **Extensible**: Clean API for future integrations

The design prioritizes simplicity, security, and researcher workflows over complex features. All components are open-source and run locally, giving users full control over their research data.
