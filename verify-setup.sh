#!/bin/bash

# PRAG-v2 Setup Verification Script

set -e

echo "🔍 PRAG-v2 Setup Verification"
echo "=============================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Docker
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker is installed: $(docker --version)"
else
    echo -e "${RED}✗${NC} Docker is not installed"
    exit 1
fi

# Check Docker Compose
echo ""
echo "2. Checking Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker Compose is installed: $(docker-compose --version)"
else
    echo -e "${RED}✗${NC} Docker Compose is not installed"
    exit 1
fi

# Check Ollama
echo ""
echo "3. Checking Ollama..."
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✓${NC} Ollama is installed"

    # Check if Ollama is running
    if ollama list &> /dev/null; then
        echo -e "${GREEN}✓${NC} Ollama is running"

        # Check for required models
        echo ""
        echo "4. Checking Ollama models..."

        if ollama list | grep -q "nomic-embed-text"; then
            echo -e "${GREEN}✓${NC} nomic-embed-text is installed"
        else
            echo -e "${YELLOW}⚠${NC} nomic-embed-text not found"
            echo "  Run: ollama pull nomic-embed-text"
        fi

        if ollama list | grep -q "llama3:"; then
            echo -e "${GREEN}✓${NC} llama3 is installed"
        else
            echo -e "${YELLOW}⚠${NC} llama3 not found"
            echo "  Run: ollama pull llama3"
            echo "  Or use alternative: ollama pull llama3.2:1b (smaller)"
        fi

        # Check for alternative models
        if ollama list | grep -q "mxbai-embed-large"; then
            echo -e "${GREEN}✓${NC} Alternative embedding model available: mxbai-embed-large"
        fi

        if ollama list | grep -q "llama3.2"; then
            echo -e "${GREEN}✓${NC} Alternative LLM available: llama3.2"
        fi
    else
        echo -e "${RED}✗${NC} Ollama is not running"
        echo "  Run: ollama serve"
        exit 1
    fi
else
    echo -e "${RED}✗${NC} Ollama is not installed"
    echo "  Install from: https://ollama.ai"
    exit 1
fi

# Check project files
echo ""
echo "5. Checking project files..."

required_files=(
    "docker-compose.yml"
    "config.yaml"
    ".env"
    "backend/Dockerfile"
    "frontend/Dockerfile"
    "backend/app/main.py"
    "frontend/app.py"
)

all_files_present=true
for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (missing)"
        all_files_present=false
    fi
done

if [ "$all_files_present" = false ]; then
    exit 1
fi

# Check data directories
echo ""
echo "6. Checking data directories..."
mkdir -p data/collections data/qdrant
echo -e "${GREEN}✓${NC} data/collections"
echo -e "${GREEN}✓${NC} data/qdrant"

# Summary
echo ""
echo "=============================="
echo "📊 Setup Summary"
echo "=============================="
echo -e "${GREEN}✓${NC} All prerequisites met!"
echo ""
echo "🚀 Ready to start PRAG-v2!"
echo ""
echo "Next steps:"
echo "1. Pull required models (if not already done):"
echo "   ollama pull nomic-embed-text"
echo "   ollama pull llama3"
echo ""
echo "2. Start services:"
echo "   docker-compose up -d"
echo ""
echo "3. Check health:"
echo "   curl http://localhost:8000/health | jq"
echo ""
echo "4. Open UI:"
echo "   http://localhost:8501"
echo ""
echo "5. Run tests:"
echo "   source .venv/bin/activate && pytest -v"
echo ""
echo "For detailed instructions, see TESTING.md"
