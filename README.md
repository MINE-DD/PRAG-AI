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
