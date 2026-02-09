# PRAG-v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local RAG system for academic research papers with PDF processing, vector search, and intelligent querying.

**Architecture:** Docker Compose orchestration with FastAPI backend (Python), Streamlit frontend (Python), Qdrant vector DB, Docling PDF processing, and Ollama/API LLM integration.

**Tech Stack:** Python 3.12, uv, FastAPI, Streamlit, Qdrant, Docling, Ollama, Docker Compose

---

## Phase 1: Project Foundation & Infrastructure

### Task 1.1: Initialize Project Structure

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `config.yaml`

**Step 1: Create .gitignore**

```bash
echo ".env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
*.egg-info/
dist/
build/
data/
.DS_Store
*.swp
*.swo" > .gitignore
```

**Step 2: Create README.md**

```markdown
# PRAG-v2

Local RAG system for academic research papers.

## Prerequisites

- Docker & Docker Compose
- Ollama (installed and running)
- Python 3.12+ (for development)

## Quick Start

1. Install Ollama models:
   ```bash
   ollama pull nomic-embed-text
   ollama pull llama3
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   ```

3. Start services:
   ```bash
   docker-compose up -d
   ```

4. Access UI: http://localhost:8501

## Development

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```
```

**Step 3: Create pyproject.toml**

```toml
[project]
name = "prag-v2"
version = "0.1.0"
description = "RAG system for academic research papers"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "qdrant-client>=1.7.0",
    "docling>=1.0.0",
    "pyyaml>=6.0",
    "python-multipart>=0.0.6",
    "httpx>=0.26.0",
    "ollama>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
]
api = [
    "anthropic>=0.18.0",
    "google-generativeai>=0.3.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 4: Create .env.example**

```bash
# Optional API keys
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

# Service URLs (default values)
QDRANT_URL=http://qdrant:6333
OLLAMA_URL=http://host.docker.internal:11434

# Data directory
DATA_DIR=/data/collections
```

**Step 5: Create config.yaml**

```yaml
models:
  embedding: "nomic-embed-text"
  llm:
    type: "local"
    model: "llama3"

chunking:
  size: 500
  overlap: 100
  strategy: "fixed"

retrieval:
  top_k: 10

citations:
  unique_id_format: "{author}{title_words}{year}"
```

**Step 6: Commit**

```bash
git add .gitignore README.md pyproject.toml .env.example config.yaml
git commit -m "feat: initialize project structure with configs"
```

---

### Task 1.2: Create Directory Structure

**Files:**
- Create: `backend/`
- Create: `frontend/`
- Create: `tests/`
- Create: `data/` (gitignored)

**Step 1: Create backend directory structure**

```bash
mkdir -p backend/app/{models,api,services,core}
touch backend/app/__init__.py
touch backend/app/main.py
touch backend/app/models/__init__.py
touch backend/app/api/__init__.py
touch backend/app/services/__init__.py
touch backend/app/core/__init__.py
```

**Step 2: Create frontend directory**

```bash
mkdir -p frontend
touch frontend/app.py
```

**Step 3: Create tests directory**

```bash
mkdir -p tests/{unit,integration}
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
```

**Step 4: Create data directories**

```bash
mkdir -p data/{collections,qdrant}
```

**Step 5: Commit**

```bash
git add backend/ frontend/ tests/
git commit -m "feat: create directory structure for backend, frontend, tests"
```

---

### Task 1.3: Docker Compose Setup

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`

**Step 1: Write docker-compose.yml**

```yaml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./data/qdrant:/qdrant/storage
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      qdrant:
        condition: service_healthy
    volumes:
      - ./data/collections:/data/collections
      - ./config.yaml:/app/config.yaml:ro
    env_file:
      - .env
    environment:
      - QDRANT_URL=http://qdrant:6333
      - OLLAMA_URL=http://host.docker.internal:11434
      - DATA_DIR=/data/collections
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  frontend:
    build: ./frontend
    ports:
      - "8501:8501"
    depends_on:
      backend:
        condition: service_healthy
    environment:
      - BACKEND_URL=http://backend:8000
    restart: unless-stopped
```

**Step 2: Write backend/Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml .

# Install uv and dependencies
RUN pip install uv && \
    uv pip install --system -e .

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 3: Write frontend/Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install streamlit and httpx
RUN pip install streamlit httpx

# Copy application code
COPY app.py .

# Expose port
EXPOSE 8501

# Run application
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

**Step 4: Commit**

```bash
git add docker-compose.yml backend/Dockerfile frontend/Dockerfile
git commit -m "feat: add Docker Compose orchestration with health checks"
```

---

## Phase 2: Core Data Models

### Task 2.1: Define Pydantic Models

**Files:**
- Create: `backend/app/models/paper.py`
- Create: `backend/app/models/collection.py`
- Create: `backend/app/models/query.py`
- Create: `tests/unit/test_models.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_models.py
import pytest
from datetime import datetime
from backend.app.models.paper import PaperMetadata, Chunk, ChunkType


def test_paper_metadata_creation():
    """Test PaperMetadata model with all fields"""
    metadata = PaperMetadata(
        paper_id="test-123",
        title="Test Paper",
        authors=["Author One", "Author Two"],
        year=2024,
        abstract="This is a test abstract",
        unique_id="AuthorTest2024"
    )

    assert metadata.paper_id == "test-123"
    assert metadata.title == "Test Paper"
    assert len(metadata.authors) == 2
    assert metadata.unique_id == "AuthorTest2024"


def test_chunk_creation():
    """Test Chunk model with required fields"""
    chunk = Chunk(
        paper_id="test-123",
        unique_id="AuthorTest2024",
        chunk_text="This is test content",
        chunk_type=ChunkType.BODY,
        page_number=1
    )

    assert chunk.paper_id == "test-123"
    assert chunk.chunk_type == ChunkType.BODY
    assert chunk.page_number == 1


def test_chunk_type_enum():
    """Test ChunkType enum values"""
    assert ChunkType.ABSTRACT == "abstract"
    assert ChunkType.BODY == "body"
    assert ChunkType.TABLE == "table"
    assert ChunkType.FIGURE_CAPTION == "figure_caption"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.app.models.paper'"

**Step 3: Write minimal implementation**

```python
# backend/app/models/paper.py
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    """Types of document chunks"""
    ABSTRACT = "abstract"
    BODY = "body"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"


class PaperMetadata(BaseModel):
    """Metadata for a research paper"""
    paper_id: str = Field(..., description="Unique paper identifier")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="List of authors")
    year: Optional[int] = Field(None, description="Publication year")
    abstract: Optional[str] = Field(None, description="Paper abstract")
    keywords: list[str] = Field(default_factory=list, description="Keywords")
    journal_conference: Optional[str] = Field(None, description="Publication venue")
    citations: list[str] = Field(default_factory=list, description="Cited papers")
    unique_id: str = Field(..., description="Human-readable citation ID")
    pdf_path: Optional[str] = Field(None, description="Path to PDF file")
    figures: list[dict] = Field(default_factory=list, description="Figure metadata")
    publication_date: Optional[str] = Field(None, description="Publication date")


class Chunk(BaseModel):
    """Document chunk for embedding"""
    paper_id: str = Field(..., description="Paper this chunk belongs to")
    unique_id: str = Field(..., description="Human-readable citation ID")
    chunk_text: str = Field(..., description="Chunk content")
    chunk_type: ChunkType = Field(..., description="Type of chunk")
    page_number: int = Field(..., description="Source page number")
    metadata: Optional[dict] = Field(None, description="Additional metadata")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py -v`
Expected: PASS (3 tests)

**Step 5: Add collection models test**

```python
# Add to tests/unit/test_models.py
from backend.app.models.collection import Collection


def test_collection_creation():
    """Test Collection model"""
    collection = Collection(
        collection_id="test-collection",
        name="Test Collection",
        description="Test description"
    )

    assert collection.collection_id == "test-collection"
    assert collection.name == "Test Collection"
    assert collection.paper_count == 0
```

**Step 6: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::test_collection_creation -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 7: Implement collection model**

```python
# backend/app/models/collection.py
from datetime import datetime
from pydantic import BaseModel, Field


class Collection(BaseModel):
    """Collection of research papers"""
    collection_id: str = Field(..., description="Unique collection identifier")
    name: str = Field(..., description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    created_date: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    paper_count: int = Field(default=0, description="Number of papers")


class CollectionResponse(BaseModel):
    """Response model for collection with papers"""
    collection_id: str
    name: str
    papers: list[dict] = Field(default_factory=list)
```

**Step 8: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py::test_collection_creation -v`
Expected: PASS

**Step 9: Add query models test**

```python
# Add to tests/unit/test_models.py
from backend.app.models.query import QueryRequest, QueryResponse, Source


def test_query_request():
    """Test QueryRequest model"""
    req = QueryRequest(
        collection_id="test-collection",
        paper_ids=["paper-1", "paper-2"],
        query_text="What is attention?"
    )

    assert req.collection_id == "test-collection"
    assert len(req.paper_ids) == 2
    assert req.chat_history == []


def test_query_response_with_sources():
    """Test QueryResponse with sources"""
    source = Source(
        unique_id="AuthorTest2024",
        title="Test Paper",
        authors=["Author"],
        year=2024,
        excerpts=["Excerpt 1"],
        pages=[1]
    )

    response = QueryResponse(
        answer="This is the answer",
        sources=[source],
        cited_paper_ids=["paper-1"]
    )

    assert "answer" in response.answer
    assert len(response.sources) == 1
    assert response.sources[0].unique_id == "AuthorTest2024"
```

**Step 10: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::test_query_request -v`
Expected: FAIL

**Step 11: Implement query models**

```python
# backend/app/models/query.py
from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request for querying papers"""
    collection_id: str = Field(..., description="Collection to query")
    paper_ids: list[str] = Field(default_factory=list, description="Paper IDs to search (empty = all)")
    query_text: str = Field(..., description="User question")
    chat_history: list[dict] = Field(default_factory=list, description="Previous messages")


class Source(BaseModel):
    """Citation source information"""
    unique_id: str = Field(..., description="Human-readable ID")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(..., description="Paper authors")
    year: Optional[int] = Field(None, description="Publication year")
    excerpts: list[str] = Field(default_factory=list, description="Relevant excerpts")
    pages: list[int] = Field(default_factory=list, description="Page numbers")


class QueryResponse(BaseModel):
    """Response from query operation"""
    answer: str = Field(..., description="Generated answer with citations")
    sources: list[Source] = Field(default_factory=list, description="Cited sources")
    cited_paper_ids: list[str] = Field(default_factory=list, description="Papers cited in answer")


class SummarizeRequest(BaseModel):
    """Request to summarize a paper"""
    collection_id: str
    paper_id: str
    chat_history: list[dict] = Field(default_factory=list)


class CompareRequest(BaseModel):
    """Request to compare papers"""
    collection_id: str
    paper_ids: list[str] = Field(..., min_length=2)
    aspect: str = Field(default="all", pattern="^(methodology|findings|all)$")
    chat_history: list[dict] = Field(default_factory=list)
```

**Step 12: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py -v`
Expected: All tests PASS

**Step 13: Commit**

```bash
git add backend/app/models/ tests/unit/test_models.py
git commit -m "feat: add Pydantic models for papers, collections, queries

- Add PaperMetadata and Chunk models with ChunkType enum
- Add Collection model with timestamps
- Add Query/Response models with Source citations
- Full test coverage for all models"
```

---

## Phase 3: Configuration & Core Services

### Task 3.1: Configuration Management

**Files:**
- Create: `backend/app/core/config.py`
- Create: `tests/unit/test_config.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_config.py
import pytest
from backend.app.core.config import Settings, load_config


def test_settings_from_env(monkeypatch):
    """Test Settings loaded from environment"""
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("DATA_DIR", "/tmp/data")

    settings = Settings()

    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.ollama_url == "http://localhost:11434"
    assert settings.data_dir == "/tmp/data"


def test_load_config_from_yaml():
    """Test loading config.yaml"""
    config = load_config("config.yaml")

    assert "models" in config
    assert "chunking" in config
    assert config["models"]["embedding"] == "nomic-embed-text"
    assert config["chunking"]["size"] == 500
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL

**Step 3: Implement configuration**

```python
# backend/app/core/config.py
from typing import Optional
from pydantic_settings import BaseSettings
import yaml
from pathlib import Path


class Settings(BaseSettings):
    """Application settings from environment"""
    qdrant_url: str = "http://qdrant:6333"
    ollama_url: str = "http://host.docker.internal:11434"
    data_dir: str = "/data/collections"
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)


# Global instances
settings = Settings()
config = load_config()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/core/config.py tests/unit/test_config.py
git commit -m "feat: add configuration management with env and yaml support"
```

---

### Task 3.2: Qdrant Client Service

**Files:**
- Create: `backend/app/services/qdrant_service.py`
- Create: `tests/unit/test_qdrant_service.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_qdrant_service.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from backend.app.services.qdrant_service import QdrantService
from backend.app.models.paper import Chunk, ChunkType


@pytest.fixture
def qdrant_service():
    """Create QdrantService with mocked client"""
    with patch('backend.app.services.qdrant_service.QdrantClient') as mock_client:
        service = QdrantService(url="http://localhost:6333")
        service.client = Mock()
        return service


def test_create_collection(qdrant_service):
    """Test creating a Qdrant collection"""
    qdrant_service.client.create_collection = Mock()

    qdrant_service.create_collection("test-collection", vector_size=768)

    qdrant_service.client.create_collection.assert_called_once()


def test_delete_collection(qdrant_service):
    """Test deleting a Qdrant collection"""
    qdrant_service.client.delete_collection = Mock()

    qdrant_service.delete_collection("test-collection")

    qdrant_service.client.delete_collection.assert_called_once_with("test-collection")


def test_upsert_chunks(qdrant_service):
    """Test upserting chunks to Qdrant"""
    chunks = [
        Chunk(
            paper_id="paper-1",
            unique_id="Test2024",
            chunk_text="Test content",
            chunk_type=ChunkType.BODY,
            page_number=1
        )
    ]
    vectors = [[0.1] * 768]

    qdrant_service.client.upsert = Mock()

    qdrant_service.upsert_chunks("test-collection", chunks, vectors)

    qdrant_service.client.upsert.assert_called_once()


def test_search_chunks(qdrant_service):
    """Test searching for chunks"""
    qdrant_service.client.search = Mock(return_value=[])

    results = qdrant_service.search(
        collection_name="test-collection",
        query_vector=[0.1] * 768,
        limit=10
    )

    assert isinstance(results, list)
    qdrant_service.client.search.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_qdrant_service.py -v`
Expected: FAIL

**Step 3: Implement Qdrant service**

```python
# backend/app/services/qdrant_service.py
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import Optional
import uuid


class QdrantService:
    """Service for interacting with Qdrant vector database"""

    def __init__(self, url: str):
        self.client = QdrantClient(url=url)

    def create_collection(self, collection_name: str, vector_size: int = 768):
        """Create a new Qdrant collection"""
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )

    def delete_collection(self, collection_name: str):
        """Delete a Qdrant collection"""
        self.client.delete_collection(collection_name=collection_name)

    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists"""
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def upsert_chunks(self, collection_name: str, chunks: list, vectors: list):
        """Upsert chunks with embeddings to Qdrant"""
        points = []
        for chunk, vector in zip(chunks, vectors):
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "paper_id": chunk.paper_id,
                    "unique_id": chunk.unique_id,
                    "chunk_text": chunk.chunk_text,
                    "chunk_type": chunk.chunk_type.value,
                    "page_number": chunk.page_number,
                    "metadata": chunk.metadata or {}
                }
            )
            points.append(point)

        self.client.upsert(collection_name=collection_name, points=points)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        paper_ids: Optional[list[str]] = None
    ) -> list:
        """Search for similar chunks"""
        query_filter = None
        if paper_ids:
            query_filter = {
                "must": [
                    {"key": "paper_id", "match": {"any": paper_ids}}
                ]
            }

        return self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter
        )

    def delete_by_paper_id(self, collection_name: str, paper_id: str):
        """Delete all chunks for a specific paper"""
        self.client.delete(
            collection_name=collection_name,
            points_selector={
                "filter": {
                    "must": [
                        {"key": "paper_id", "match": {"value": paper_id}}
                    ]
                }
            }
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_qdrant_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/qdrant_service.py tests/unit/test_qdrant_service.py
git commit -m "feat: add Qdrant service for vector database operations"
```

---

### Task 3.3: Ollama Client Service

**Files:**
- Create: `backend/app/services/ollama_service.py`
- Create: `tests/unit/test_ollama_service.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_ollama_service.py
import pytest
from unittest.mock import Mock, patch
from backend.app.services.ollama_service import OllamaService


@pytest.fixture
def ollama_service():
    """Create OllamaService with mocked client"""
    with patch('backend.app.services.ollama_service.ollama') as mock_ollama:
        service = OllamaService(url="http://localhost:11434", model="llama3")
        service.client = mock_ollama
        return service


def test_generate_embedding(ollama_service):
    """Test generating embeddings"""
    ollama_service.client.embeddings = Mock(return_value={"embedding": [0.1] * 768})

    embedding = ollama_service.generate_embedding("test text")

    assert len(embedding) == 768
    ollama_service.client.embeddings.assert_called_once()


def test_generate_embeddings_batch(ollama_service):
    """Test batch embedding generation"""
    ollama_service.client.embeddings = Mock(return_value={"embedding": [0.1] * 768})

    texts = ["text 1", "text 2", "text 3"]
    embeddings = ollama_service.generate_embeddings_batch(texts)

    assert len(embeddings) == 3
    assert ollama_service.client.embeddings.call_count == 3


def test_generate_response(ollama_service):
    """Test generating LLM response"""
    ollama_service.client.chat = Mock(return_value={
        "message": {"content": "This is a response"}
    })

    response = ollama_service.generate(
        prompt="Test prompt",
        system="You are a helpful assistant"
    )

    assert "response" in response
    ollama_service.client.chat.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ollama_service.py -v`
Expected: FAIL

**Step 3: Implement Ollama service**

```python
# backend/app/services/ollama_service.py
import ollama
from typing import Optional


class OllamaService:
    """Service for interacting with Ollama LLMs"""

    def __init__(self, url: str, model: str = "llama3", embedding_model: str = "nomic-embed-text"):
        self.url = url
        self.model = model
        self.embedding_model = embedding_model
        self.client = ollama.Client(host=url)

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text"""
        response = self.client.embeddings(
            model=self.embedding_model,
            prompt=text
        )
        return response["embedding"]

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts"""
        embeddings = []
        for text in texts:
            embedding = self.generate_embedding(text)
            embeddings.append(embedding)
        return embeddings

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        chat_history: Optional[list[dict]] = None
    ) -> str:
        """Generate text response from LLM"""
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": temperature}
        )

        return response["message"]["content"]

    def check_health(self) -> bool:
        """Check if Ollama is accessible"""
        try:
            self.client.list()
            return True
        except Exception:
            return False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ollama_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/ollama_service.py tests/unit/test_ollama_service.py
git commit -m "feat: add Ollama service for embeddings and generation"
```

---

## Phase 4: PDF Processing Pipeline

### Task 4.1: Chunking Service

**Files:**
- Create: `backend/app/services/chunking_service.py`
- Create: `tests/unit/test_chunking_service.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_chunking_service.py
import pytest
from backend.app.services.chunking_service import ChunkingService


def test_chunk_text_fixed_size():
    """Test fixed-size chunking"""
    service = ChunkingService(chunk_size=50, overlap=10)

    text = "This is a test text. " * 20  # Long text
    chunks = service.chunk_text(text)

    assert len(chunks) > 1
    for chunk in chunks[:-1]:  # All but last
        assert len(chunk) >= 40  # At least chunk_size - overlap


def test_chunk_text_with_overlap():
    """Test chunking with overlap"""
    service = ChunkingService(chunk_size=50, overlap=10)

    text = "A" * 100
    chunks = service.chunk_text(text)

    # Check overlap between consecutive chunks
    if len(chunks) > 1:
        assert chunks[0][-10:] == chunks[1][:10]


def test_chunk_short_text():
    """Test chunking text shorter than chunk_size"""
    service = ChunkingService(chunk_size=500, overlap=100)

    text = "Short text"
    chunks = service.chunk_text(text)

    assert len(chunks) == 1
    assert chunks[0] == text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_chunking_service.py -v`
Expected: FAIL

**Step 3: Implement chunking service**

```python
# backend/app/services/chunking_service.py
from typing import List


class ChunkingService:
    """Service for chunking text into smaller pieces"""

    def __init__(self, chunk_size: int = 500, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> List[str]:
        """
        Chunk text using fixed-size strategy with overlap.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)

            # Move start forward by (chunk_size - overlap)
            start += (self.chunk_size - self.overlap)

            # Break if we've reached the end
            if end >= len(text):
                break

        return chunks

    def chunk_by_paragraphs(self, text: str) -> List[str]:
        """
        Chunk text by paragraph boundaries (for future use).

        Args:
            text: Text to chunk

        Returns:
            List of paragraphs
        """
        # Split by double newline (paragraph separator)
        paragraphs = text.split('\n\n')
        return [p.strip() for p in paragraphs if p.strip()]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_chunking_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/chunking_service.py tests/unit/test_chunking_service.py
git commit -m "feat: add chunking service with fixed-size and overlap support"
```

---

### Task 4.2: Docling PDF Processor

**Files:**
- Create: `backend/app/services/pdf_processor.py`
- Create: `tests/unit/test_pdf_processor.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_pdf_processor.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from backend.app.services.pdf_processor import PDFProcessor
from backend.app.models.paper import PaperMetadata


@pytest.fixture
def pdf_processor():
    """Create PDFProcessor"""
    return PDFProcessor()


def test_generate_unique_id():
    """Test unique ID generation"""
    processor = PDFProcessor()

    title = "Attention Is All You Need"
    authors = ["Vaswani", "Shazeer"]
    year = 2017

    unique_id = processor.generate_unique_id(title, authors, year)

    assert "Vaswani" in unique_id
    assert "Attention" in unique_id
    assert "2017" in unique_id


def test_extract_metadata_from_doc():
    """Test metadata extraction from docling document"""
    processor = PDFProcessor()

    # Mock docling document
    mock_doc = MagicMock()
    mock_doc.title = "Test Paper"
    mock_doc.authors = ["Author One", "Author Two"]
    mock_doc.abstract = "This is the abstract"
    mock_doc.publication_date = "2024"

    metadata = processor.extract_metadata(mock_doc, paper_id="test-123")

    assert metadata.title == "Test Paper"
    assert len(metadata.authors) == 2
    assert metadata.abstract == "This is the abstract"
    assert "2024" in metadata.unique_id or "Author" in metadata.unique_id
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pdf_processor.py -v`
Expected: FAIL

**Step 3: Implement PDF processor (partial - metadata only)**

```python
# backend/app/services/pdf_processor.py
from docling.document_converter import DocumentConverter
from pathlib import Path
from typing import Optional
import re
from backend.app.models.paper import PaperMetadata


class PDFProcessor:
    """Service for processing PDFs with Docling"""

    def __init__(self):
        self.converter = DocumentConverter()

    def generate_unique_id(
        self,
        title: Optional[str],
        authors: Optional[list[str]],
        year: Optional[int]
    ) -> str:
        """
        Generate human-readable unique ID from paper metadata.
        Format: FirstAuthorLastNameTitleWordsYear
        """
        parts = []

        # Add first author last name
        if authors and len(authors) > 0:
            author = authors[0].split()[-1]  # Last word is last name
            author = re.sub(r'[^a-zA-Z]', '', author)  # Remove non-letters
            parts.append(author)

        # Add first 1-2 words from title
        if title:
            title_words = title.split()[:2]
            title_part = ''.join(w.capitalize() for w in title_words)
            title_part = re.sub(r'[^a-zA-Z]', '', title_part)
            parts.append(title_part)

        # Add year
        if year:
            parts.append(str(year))

        # Fallback
        if not parts:
            return "UnknownPaper"

        return ''.join(parts)

    def extract_metadata(self, doc, paper_id: str) -> PaperMetadata:
        """
        Extract metadata from Docling document.

        Args:
            doc: Docling document object
            paper_id: Unique paper identifier

        Returns:
            PaperMetadata object
        """
        # Extract basic metadata
        title = getattr(doc, 'title', None) or "Untitled"
        authors = getattr(doc, 'authors', []) or []
        abstract = getattr(doc, 'abstract', None)
        publication_date = getattr(doc, 'publication_date', None)

        # Extract year from publication date
        year = None
        if publication_date:
            year_match = re.search(r'\d{4}', str(publication_date))
            if year_match:
                year = int(year_match.group())

        # Generate unique ID
        unique_id = self.generate_unique_id(title, authors, year)

        return PaperMetadata(
            paper_id=paper_id,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            unique_id=unique_id,
            publication_date=publication_date
        )

    def process_pdf(self, pdf_path: Path, paper_id: str) -> dict:
        """
        Process PDF and extract all content.

        Args:
            pdf_path: Path to PDF file
            paper_id: Unique paper identifier

        Returns:
            Dictionary with metadata, text, tables, figures
        """
        # Convert PDF
        result = self.converter.convert(str(pdf_path))
        doc = result.document

        # Extract metadata
        metadata = self.extract_metadata(doc, paper_id)

        # Extract text content
        text_content = doc.export_to_text()

        # TODO: Extract tables and figures (Phase 4.3)

        return {
            "metadata": metadata,
            "text": text_content,
            "tables": [],
            "figures": []
        }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pdf_processor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/pdf_processor.py tests/unit/test_pdf_processor.py
git commit -m "feat: add PDF processor with Docling for metadata extraction"
```

---

## Phase 5: API Endpoints - Collection Management

### Task 5.1: Health Check Endpoint

**Files:**
- Create: `backend/app/api/health.py`
- Create: `backend/app/main.py`
- Create: `tests/integration/test_health_api.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_health_api.py
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "qdrant" in data
    assert "ollama" in data
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_health_api.py -v`
Expected: FAIL

**Step 3: Implement main app**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api import health
from backend.app.core.config import settings

app = FastAPI(
    title="PRAG-v2 API",
    description="RAG system for academic research papers",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])


@app.get("/")
def root():
    return {"message": "PRAG-v2 API", "version": "0.1.0"}
```

**Step 4: Implement health endpoint**

```python
# backend/app/api/health.py
from fastapi import APIRouter
from backend.app.core.config import settings
from backend.app.services.qdrant_service import QdrantService
from backend.app.services.ollama_service import OllamaService

router = APIRouter()


@router.get("/health")
def health_check():
    """Check health of all services"""
    health_status = {
        "api": "ok",
        "qdrant": "error",
        "ollama": "error",
        "models": {
            "embedding": "unknown",
            "llm": "unknown"
        }
    }

    # Check Qdrant
    try:
        qdrant = QdrantService(url=settings.qdrant_url)
        if qdrant.client.get_collections():
            health_status["qdrant"] = "ok"
    except Exception:
        pass

    # Check Ollama
    try:
        ollama = OllamaService(url=settings.ollama_url)
        if ollama.check_health():
            health_status["ollama"] = "ok"
            health_status["models"]["embedding"] = "ok"
            health_status["models"]["llm"] = "ok"
    except Exception:
        pass

    return health_status
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/integration/test_health_api.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/main.py backend/app/api/health.py tests/integration/test_health_api.py
git commit -m "feat: add FastAPI app with health check endpoint"
```

---

### Task 5.2: Collection Management Endpoints

**Files:**
- Create: `backend/app/api/collections.py`
- Create: `backend/app/services/collection_service.py`
- Create: `tests/integration/test_collections_api.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_collections_api.py
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_create_collection(client):
    """Test creating a new collection"""
    response = client.post(
        "/collections",
        json={"name": "Test Collection", "description": "Test"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "collection_id" in data
    assert data["name"] == "Test Collection"


def test_list_collections(client):
    """Test listing collections"""
    response = client.get("/collections")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_collection(client):
    """Test getting a specific collection"""
    # First create a collection
    create_response = client.post(
        "/collections",
        json={"name": "Test Collection 2"}
    )
    collection_id = create_response.json()["collection_id"]

    # Then get it
    response = client.get(f"/collections/{collection_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["collection_id"] == collection_id


def test_delete_collection(client):
    """Test deleting a collection"""
    # Create collection
    create_response = client.post(
        "/collections",
        json={"name": "Delete Me"}
    )
    collection_id = create_response.json()["collection_id"]

    # Delete it
    response = client.delete(f"/collections/{collection_id}")

    assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_collections_api.py -v`
Expected: FAIL

**Step 3: Implement collection service**

```python
# backend/app/services/collection_service.py
from pathlib import Path
from datetime import datetime
import uuid
import shutil
from typing import Optional
from backend.app.models.collection import Collection
from backend.app.services.qdrant_service import QdrantService
from backend.app.core.config import settings


class CollectionService:
    """Service for managing collections"""

    def __init__(self, qdrant: QdrantService):
        self.qdrant = qdrant
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create_collection(self, name: str, description: Optional[str] = None) -> Collection:
        """Create a new collection"""
        # Generate collection ID (sanitized name)
        collection_id = name.lower().replace(" ", "_")

        # Check if already exists
        collection_path = self.data_dir / collection_id
        if collection_path.exists():
            raise ValueError(
                f'Collection "{name}" already exists at {collection_path}. '
                f'Please use a different name or reprocess the existing collection.'
            )

        # Create directories
        collection_path.mkdir(parents=True)
        (collection_path / "pdfs").mkdir()
        (collection_path / "figures").mkdir()

        # Create Qdrant collection
        self.qdrant.create_collection(collection_id)

        return Collection(
            collection_id=collection_id,
            name=name,
            description=description
        )

    def list_collections(self) -> list[Collection]:
        """List all collections"""
        collections = []

        for path in self.data_dir.iterdir():
            if path.is_dir():
                # Count PDFs
                pdf_count = len(list((path / "pdfs").glob("*.pdf")))

                collections.append(Collection(
                    collection_id=path.name,
                    name=path.name.replace("_", " ").title(),
                    paper_count=pdf_count,
                    created_date=datetime.fromtimestamp(path.stat().st_ctime),
                    last_updated=datetime.fromtimestamp(path.stat().st_mtime)
                ))

        return collections

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a specific collection"""
        collection_path = self.data_dir / collection_id

        if not collection_path.exists():
            return None

        pdf_count = len(list((collection_path / "pdfs").glob("*.pdf")))

        return Collection(
            collection_id=collection_id,
            name=collection_id.replace("_", " ").title(),
            paper_count=pdf_count,
            created_date=datetime.fromtimestamp(collection_path.stat().st_ctime),
            last_updated=datetime.fromtimestamp(collection_path.stat().st_mtime)
        )

    def delete_collection(self, collection_id: str):
        """Delete collection (Qdrant only, keep files)"""
        # Delete from Qdrant
        if self.qdrant.collection_exists(collection_id):
            self.qdrant.delete_collection(collection_id)

    def delete_collection_files(self, collection_id: str):
        """Delete collection files (for testing)"""
        collection_path = self.data_dir / collection_id
        if collection_path.exists():
            shutil.rmtree(collection_path)
```

**Step 4: Implement API endpoints**

```python
# backend/app/api/collections.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from backend.app.services.collection_service import CollectionService
from backend.app.services.qdrant_service import QdrantService
from backend.app.core.config import settings
from backend.app.models.collection import Collection

router = APIRouter()


class CreateCollectionRequest(BaseModel):
    name: str
    description: str = None


def get_collection_service():
    """Dependency to get collection service"""
    qdrant = QdrantService(url=settings.qdrant_url)
    return CollectionService(qdrant=qdrant)


@router.post("/collections", response_model=Collection)
def create_collection(request: CreateCollectionRequest):
    """Create a new collection"""
    service = get_collection_service()

    try:
        return service.create_collection(
            name=request.name,
            description=request.description
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.get("/collections", response_model=list[Collection])
def list_collections():
    """List all collections"""
    service = get_collection_service()
    return service.list_collections()


@router.get("/collections/{collection_id}", response_model=Collection)
def get_collection(collection_id: str):
    """Get a specific collection"""
    service = get_collection_service()
    collection = service.get_collection(collection_id)

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection '{collection_id}' not found"
        )

    return collection


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str):
    """Delete a collection (Qdrant only, keeps files)"""
    service = get_collection_service()
    service.delete_collection(collection_id)
    return {"success": True}
```

**Step 5: Update main.py to include router**

```python
# Add to backend/app/main.py after health router
from backend.app.api import collections

app.include_router(collections.router, tags=["collections"])
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/integration/test_collections_api.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add backend/app/api/collections.py backend/app/services/collection_service.py tests/integration/test_collections_api.py backend/app/main.py
git commit -m "feat: add collection management endpoints with create/list/get/delete"
```

---

## Phase 6: Frontend - Basic Streamlit UI

### Task 6.1: Basic Streamlit App Structure

**Files:**
- Create: `frontend/app.py`

**Step 1: Write basic Streamlit app**

```python
# frontend/app.py
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
```

**Step 2: Test manually**

Run: `streamlit run frontend/app.py`
Expected: UI loads, can create/list collections

**Step 3: Commit**

```bash
git add frontend/app.py
git commit -m "feat: add basic Streamlit UI with collection management"
```

---

## Phase 7: Integration & Testing

### Task 7.1: End-to-End Test Setup

**Files:**
- Create: `tests/e2e/test_basic_flow.py`
- Create: `.github/workflows/ci.yml` (optional)

**Step 1: Write end-to-end test**

```python
# tests/e2e/test_basic_flow.py
import pytest
import httpx
import time


@pytest.fixture(scope="module")
def backend_url():
    """Backend URL for testing"""
    return "http://localhost:8000"


@pytest.fixture(scope="module")
def wait_for_backend(backend_url):
    """Wait for backend to be ready"""
    for _ in range(30):
        try:
            response = httpx.get(f"{backend_url}/health")
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    pytest.fail("Backend not ready")


def test_complete_flow(backend_url, wait_for_backend):
    """Test complete workflow: create collection -> list -> delete"""
    client = httpx.Client(base_url=backend_url)

    # Create collection
    response = client.post(
        "/collections",
        json={"name": "E2E Test Collection"}
    )
    assert response.status_code == 200
    collection_id = response.json()["collection_id"]

    # List collections
    response = client.get("/collections")
    assert response.status_code == 200
    collections = response.json()
    assert any(c["collection_id"] == collection_id for c in collections)

    # Get collection
    response = client.get(f"/collections/{collection_id}")
    assert response.status_code == 200

    # Delete collection
    response = client.delete(f"/collections/{collection_id}")
    assert response.status_code == 200
```

**Step 2: Run test**

Run: `docker-compose up -d && pytest tests/e2e/test_basic_flow.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/e2e/test_basic_flow.py
git commit -m "test: add end-to-end test for basic collection workflow"
```

---

## Remaining Implementation Tasks

**Note:** The plan above covers Phases 1-7 (foundation, models, services, basic API, basic UI). The remaining phases are outlined below at a high level. Each should follow the same TDD approach with bite-sized steps.

### Phase 8: PDF Upload & Processing
- Task 8.1: File upload endpoint
- Task 8.2: Processing pipeline integration
- Task 8.3: Background job handling
- Task 8.4: Progress tracking

### Phase 9: Query System
- Task 9.1: Query endpoint with semantic search
- Task 9.2: Citation generation
- Task 9.3: Summarize endpoint
- Task 9.4: Compare endpoint

### Phase 10: Frontend Enhancement
- Task 10.1: PDF upload UI
- Task 10.2: Paper selection panel
- Task 10.3: Chat interface
- Task 10.4: Smart paper ordering
- Task 10.5: Export to markdown

### Phase 11: External LLM Support
- Task 11.1: LLM router abstraction
- Task 11.2: Anthropic client
- Task 11.3: Google client
- Task 11.4: API key management
- Task 11.5: Settings UI

### Phase 12: Error Handling & Polish
- Task 12.1: Comprehensive error handling
- Task 12.2: Logging
- Task 12.3: Documentation
- Task 12.4: Performance optimization

---

## Testing Strategy

**Unit Tests:**
- All services (Qdrant, Ollama, Chunking, PDF Processing)
- All models (validation, serialization)
- Business logic (unique ID generation, chunking)

**Integration Tests:**
- API endpoints with test client
- Service interactions (collection → Qdrant)
- File system operations

**End-to-End Tests:**
- Complete workflows through Docker
- Real PDF processing
- Real queries with Ollama

**Test Commands:**
```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# E2E tests (requires Docker)
docker-compose up -d
pytest tests/e2e/ -v

# Coverage
pytest --cov=backend/app --cov-report=html
```

---

## Execution Notes

1. **Follow TDD strictly**: Write test → Run (fail) → Implement → Run (pass) → Commit
2. **Keep commits small**: Each task = one commit
3. **Run tests frequently**: After every implementation step
4. **Use YAGNI**: Only implement what's needed for current task
5. **DRY when appropriate**: Extract duplicates after second occurrence
6. **Document as you go**: Update README with setup instructions

---

## Plan Complete

This implementation plan provides bite-sized, testable tasks following TDD principles. Each step is 2-5 minutes of focused work with clear success criteria.

The plan prioritizes:
- ✅ Foundation and infrastructure first
- ✅ Core data models with validation
- ✅ Services layer with mocked tests
- ✅ API endpoints with integration tests
- ✅ Basic UI to validate end-to-end flow
- ✅ Incremental feature addition

**Next Steps:** Choose execution approach (subagent-driven or parallel session).
