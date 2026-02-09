# PRAG-v2 Testing Guide

## Prerequisites

✅ Docker and Docker Compose installed
✅ Ollama installed and running
⚠️ Required Ollama models (see below)

## Step 1: Install Required Ollama Models

The system requires two models:

```bash
# Pull embedding model (237 MB)
ollama pull nomic-embed-text

# Pull LLM model (4.7 GB)
ollama pull llama3
```

**Note:** If you prefer smaller/faster models, you can use:
```bash
# Alternative: Use llama3.2:1b (already installed, smaller but less capable)
ollama pull llama3.2:1b
```

If using alternative models, update `config.yaml`:
```yaml
models:
  embedding: "mxbai-embed-large"  # Already installed
  llm:
    type: "local"
    model: "llama3.2:1b"  # Already installed
```

## Step 2: Start the Services

```bash
# Start all services (Qdrant, Backend, Frontend)
docker-compose up -d

# Watch logs
docker-compose logs -f
```

Services will start in this order:
1. **Qdrant** (vector database) - http://localhost:6333
2. **Backend** (FastAPI) - http://localhost:8000
3. **Frontend** (Streamlit) - http://localhost:8501

## Step 3: Test Backend Health

```bash
# Check health endpoint
curl http://localhost:8000/health | jq

# Expected output:
# {
#   "api": "ok",
#   "qdrant": "ok",
#   "ollama": "ok",
#   "models": {
#     "embedding": "ok",
#     "llm": "ok"
#   }
# }
```

## Step 4: Test Collection API

```bash
# Create a collection
curl -X POST http://localhost:8000/collections \
  -H "Content-Type: application/json" \
  -d '{"name": "My First Collection", "description": "Test collection"}' | jq

# List collections
curl http://localhost:8000/collections | jq

# Get specific collection
curl http://localhost:8000/collections/my_first_collection | jq
```

## Step 5: Test Frontend UI

1. Open browser to http://localhost:8501
2. You should see the PRAG-v2 interface
3. Try creating a collection:
   - Click "➕ Create New Collection" in sidebar
   - Enter name: "Test Collection"
   - Click "Create"
4. Verify the collection appears in the dropdown
5. Select the collection

## Step 6: Run Automated Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
pytest -v

# Run specific test suites
pytest tests/unit/ -v           # Unit tests only
pytest tests/integration/ -v    # Integration tests only

# With coverage
pytest --cov=backend/app --cov-report=html
open htmlcov/index.html
```

## Step 7: Verify Data Persistence

```bash
# Check data directory structure
ls -la data/collections/

# After creating a collection, you should see:
# data/collections/my_first_collection/
#   ├── pdfs/
#   └── figures/
```

## Troubleshooting

### Backend won't start
```bash
# Check backend logs
docker-compose logs backend

# Common issues:
# - Qdrant not healthy: Wait for Qdrant to start
# - Ollama not accessible: Check OLLAMA_URL in .env
# - Port 8000 already in use: Stop conflicting service
```

### Frontend can't connect to backend
```bash
# Check if backend is accessible
curl http://localhost:8000/

# Verify BACKEND_URL environment variable
docker-compose exec frontend env | grep BACKEND_URL
```

### Ollama models not loading
```bash
# Verify models are pulled
ollama list

# Test embedding model
ollama run nomic-embed-text "test"

# Test LLM model
ollama run llama3 "Say hello"
```

### "Read-only file system" errors
```bash
# Ensure data directory exists and is writable
mkdir -p data/collections data/qdrant
chmod -R 755 data/
```

## Clean Up

```bash
# Stop services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove test collections
rm -rf data/collections/*
```

## What's Working Now

✅ Project structure and configuration
✅ Docker Compose orchestration
✅ Pydantic data models
✅ Qdrant vector database integration
✅ Ollama LLM integration
✅ PDF processing with Docling
✅ Text chunking service
✅ Collection management API (CRUD)
✅ Health check endpoint
✅ Streamlit UI with collection management
✅ 25 automated tests (20 unit + 5 integration)

## Not Yet Implemented

⏳ PDF upload endpoint
⏳ PDF processing workflow
⏳ Query/search endpoints
⏳ Chat interface
⏳ Citation generation
⏳ Summarization
⏳ Paper comparison

## Next Steps

According to the implementation plan:
- **Phase 7:** End-to-End Testing
- **Phase 8:** PDF Upload & Processing
- **Phase 9:** Query System
- **Phase 10:** Frontend Enhancement
- **Phase 11:** External LLM Support
- **Phase 12:** Error Handling & Polish
