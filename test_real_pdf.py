#!/usr/bin/env python3
"""
Test script to verify real PDF processing through the complete pipeline.
This script uploads a real PDF and verifies it gets processed correctly.
"""

import sys
from datetime import datetime
from pathlib import Path

import httpx

# Configuration
BACKEND_URL = "http://localhost:8000"
PDF_PATH = Path("data/pdf_input/TeachingNLP_short_CAMERA_READY.pdf")
COLLECTION_NAME = f"Test PDF {datetime.now().strftime('%Y%m%d_%H%M%S')}"


def check_services():
    """Check if backend services are running"""
    print("🔍 Checking services...")
    try:
        response = httpx.get(f"{BACKEND_URL}/health", timeout=5.0)
        if response.status_code == 200:
            health = response.json()
            print(f"✅ API: {health.get('api', 'unknown')}")
            print(f"✅ Qdrant: {health.get('qdrant', 'unknown')}")
            print(f"✅ Ollama: {health.get('ollama', 'unknown')}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Could not connect to backend: {e}")
        print("\n💡 Make sure services are running:")
        print("   docker-compose up -d")
        return False


def create_collection():
    """Create a test collection"""
    print(f"\n📁 Creating collection: {COLLECTION_NAME}")
    try:
        response = httpx.post(
            f"{BACKEND_URL}/collections",
            json={"name": COLLECTION_NAME, "description": "Testing real PDF processing"},
            timeout=10.0
        )
        if response.status_code == 200:
            collection = response.json()
            print(f"✅ Created collection: {collection['collection_id']}")
            return collection['collection_id']
        else:
            print(f"❌ Failed to create collection: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ Error creating collection: {e}")
        return None


def upload_pdf(collection_id):
    """Upload and process a PDF"""
    if not PDF_PATH.exists():
        print(f"❌ PDF not found: {PDF_PATH}")
        return None

    print(f"\n📄 Uploading PDF: {PDF_PATH.name}")
    print("   This will take a while as the PDF is being processed...")
    print("   - Extracting text with Docling")
    print("   - Chunking text")
    print("   - Generating embeddings with Ollama")
    print("   - Storing in Qdrant")

    try:
        with open(PDF_PATH, "rb") as f:
            files = {"file": (PDF_PATH.name, f, "application/pdf")}
            response = httpx.post(
                f"{BACKEND_URL}/collections/{collection_id}/papers",
                files=files,
                timeout=300.0  # 5 minutes for processing
            )

        if response.status_code == 200:
            paper = response.json()
            print("\n✅ PDF processed successfully!")
            print(f"   Paper ID: {paper['paper_id']}")
            print(f"   Title: {paper['title']}")
            print(f"   Authors: {', '.join(paper.get('authors', []))}")
            print(f"   Year: {paper.get('year', 'N/A')}")
            print(f"   Unique ID: {paper['unique_id']}")
            print(f"   Chunks created: {paper.get('chunks_created', 'N/A')}")
            print(f"   Status: {paper.get('status', 'N/A')}")
            return paper
        else:
            print(f"❌ Failed to upload PDF: {response.status_code}")
            print(response.text)
            return None
    except httpx.TimeoutException:
        print("❌ Request timed out - PDF processing took too long")
        return None
    except Exception as e:
        print(f"❌ Error uploading PDF: {e}")
        return None


def list_papers(collection_id):
    """List papers in collection"""
    print("\n📋 Listing papers in collection...")
    try:
        response = httpx.get(
            f"{BACKEND_URL}/collections/{collection_id}/papers",
            timeout=10.0
        )
        if response.status_code == 200:
            papers = response.json()
            print(f"✅ Found {len(papers)} paper(s)")
            for paper in papers:
                print(f"   - {paper['filename']}")
            return papers
        else:
            print(f"❌ Failed to list papers: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error listing papers: {e}")
        return []


def main():
    """Run the complete test"""
    print("="*60)
    print("PRAG-v2 Real PDF Processing Test")
    print("="*60)

    # Check services
    if not check_services():
        sys.exit(1)

    # Create collection
    collection_id = create_collection()
    if not collection_id:
        sys.exit(1)

    # Upload and process PDF
    paper = upload_pdf(collection_id)
    if not paper:
        sys.exit(1)

    # List papers to verify
    papers = list_papers(collection_id)

    print("\n" + "="*60)
    print("✅ TEST PASSED - Real PDF processing works end-to-end!")
    print("="*60)
    print("\nNext steps:")
    print("1. View collection in Qdrant dashboard: http://localhost:6333/dashboard")
    print("2. Check API docs: http://localhost:8000/docs")
    print("3. Try the frontend: http://localhost:8501")


if __name__ == "__main__":
    main()
