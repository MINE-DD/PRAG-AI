import json
import re
import shutil
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional

from app.models.paper import Chunk, ChunkType, PaperMetadata
from app.services.chunking_service import ChunkingService
from app.services.ollama_service import OllamaService
from app.services.qdrant_service import QdrantService
from app.services.sparse_embedding_service import SparseEmbeddingService
from app.core.config import settings


class IngestionService:
    """Service for ingesting preprocessed markdown files into a collection."""

    def __init__(
        self,
        chunking_service: ChunkingService,
        ollama_service: OllamaService,
        qdrant_service: QdrantService,
        sparse_embedding_service: Optional[SparseEmbeddingService] = None,
    ):
        self.chunking_service = chunking_service
        self.ollama_service = ollama_service
        self.qdrant_service = qdrant_service
        self.sparse_embedding_service = sparse_embedding_service
        self.data_dir = Path(settings.data_dir)

    def scan_preprocessed(self, path: str) -> dict:
        """Find markdown files in a preprocessed directory and check for metadata.

        Also counts total PDFs in the corresponding pdf_input directory.
        """
        preprocessed_path = Path(path)
        if not preprocessed_path.is_dir():
            raise FileNotFoundError(f"Preprocessed directory not found: {path}")

        files = []
        for md_file in sorted(preprocessed_path.glob("*.md")):
            stem = md_file.stem
            metadata_path = preprocessed_path / f"{stem}_metadata.json"
            files.append({
                "markdown_file": md_file.name,
                "has_metadata": metadata_path.exists(),
                "stem": stem,
            })

        # Count total PDFs in the corresponding pdf_input directory
        dir_name = preprocessed_path.name
        pdf_input_dir = Path(settings.pdf_input_dir) / dir_name
        total_pdfs = len(list(pdf_input_dir.glob("*.pdf"))) if pdf_input_dir.is_dir() else 0

        return {"files": files, "total_pdfs": total_pdfs}

    def create_collection(
        self,
        collection_id: str,
        name: str,
        description: Optional[str] = None,
        search_type: str = "dense",
    ) -> dict:
        """Create a Qdrant collection and directory structure."""
        collection_path = self.data_dir / collection_id
        if collection_path.exists():
            raise ValueError(f"Collection '{collection_id}' already exists")

        collection_path.mkdir(parents=True)
        (collection_path / "pdfs").mkdir()
        (collection_path / "figures").mkdir()
        (collection_path / "metadata").mkdir()

        # Detect embedding dimension from model and create Qdrant collection
        sample_embedding = self.ollama_service.generate_embedding("test")
        vector_size = len(sample_embedding)
        self.qdrant_service.create_collection(
            collection_id, vector_size=vector_size, search_type=search_type,
        )

        # Write collection_info.json
        info = {
            "collection_id": collection_id,
            "name": name,
            "description": description,
            "search_type": search_type,
            "created_at": datetime.now(UTC).isoformat(),
        }
        info_path = collection_path / "collection_info.json"
        info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")

        return info

    def _is_hybrid_collection(self, collection_id: str) -> bool:
        """Check if a collection uses hybrid search by reading collection_info.json."""
        info_path = self.data_dir / collection_id / "collection_info.json"
        if info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            return info.get("search_type") == "hybrid"
        return False

    def ingest_file(
        self,
        collection_id: str,
        md_path: str,
        metadata_path: Optional[str] = None,
    ) -> dict:
        """Ingest a single markdown file into a collection.

        1. Read markdown text
        2. Load metadata JSON if available
        3. Chunk text
        4. Generate embeddings
        5. Store in Qdrant
        6. Copy metadata JSON to collection's metadata/ dir
        """
        md_file = Path(md_path)
        if not md_file.exists():
            raise FileNotFoundError(f"Markdown file not found: {md_path}")

        # Read markdown content
        text_content = md_file.read_text(encoding="utf-8")

        # Load metadata if available
        metadata = {}
        if metadata_path:
            meta_file = Path(metadata_path)
            if meta_file.exists():
                metadata = json.loads(meta_file.read_text(encoding="utf-8"))

        # Derive paper_id from filename stem
        paper_id = md_file.stem

        # Build unique_id from metadata
        unique_id = self._generate_unique_id(
            title=metadata.get("title", paper_id),
            authors=metadata.get("authors", []),
            year=self._extract_year(metadata.get("publication_date")),
        )

        # Strip references section before chunking
        body_text, references = self._split_references(text_content)

        # Chunk text (body only, no references)
        text_chunks = self.chunking_service.chunk_text(body_text)

        # Create Chunk objects
        chunks = []
        for i, chunk_text in enumerate(text_chunks):
            chunk = Chunk(
                paper_id=paper_id,
                unique_id=unique_id,
                chunk_text=chunk_text,
                chunk_type=ChunkType.BODY,
                page_number=1,
                metadata={"chunk_index": i},
            )
            chunks.append(chunk)

        # Generate embeddings
        chunk_texts = [c.chunk_text for c in chunks]
        embeddings = self.ollama_service.generate_embeddings_batch(chunk_texts)

        # Generate sparse embeddings for hybrid collections
        sparse_vectors = None
        if self._is_hybrid_collection(collection_id) and self.sparse_embedding_service:
            sparse_vectors = self.sparse_embedding_service.generate_sparse_embeddings_batch(chunk_texts)

        # Store in Qdrant
        self.qdrant_service.upsert_chunks(
            collection_name=collection_id,
            chunks=chunks,
            vectors=embeddings,
            sparse_vectors=sparse_vectors,
        )

        # Copy metadata JSON to collection's metadata/ dir
        collection_meta_dir = self.data_dir / collection_id / "metadata"
        collection_meta_dir.mkdir(parents=True, exist_ok=True)

        paper_meta = {
            **metadata,
            "paper_id": paper_id,
            "unique_id": unique_id,
            "preprocessed_dir": md_file.parent.name,
            "chunks_created": len(chunks),
            "references": references,
            "ingested_at": datetime.now(UTC).isoformat(),
        }
        dest = collection_meta_dir / f"{paper_id}.json"
        dest.write_text(json.dumps(paper_meta, indent=2), encoding="utf-8")

        return {
            "paper_id": paper_id,
            "unique_id": unique_id,
            "chunks_created": len(chunks),
            "embeddings_generated": len(embeddings),
        }

    def _generate_unique_id(
        self,
        title: str,
        authors: list[str],
        year: Optional[int],
    ) -> str:
        """Generate a human-readable unique ID from metadata."""
        parts = []
        if authors:
            author = authors[0].split()[-1]
            author = re.sub(r"[^a-zA-Z]", "", author)
            parts.append(author)
        if title:
            title_words = title.split()[:2]
            title_part = "".join(w.capitalize() for w in title_words)
            title_part = re.sub(r"[^a-zA-Z]", "", title_part)
            parts.append(title_part)
        if year:
            parts.append(str(year))
        return "".join(parts) or "UnknownPaper"

    def _extract_year(self, publication_date: Optional[str]) -> Optional[int]:
        """Extract year from a publication date string."""
        if not publication_date:
            return None
        match = re.search(r"\d{4}", str(publication_date))
        return int(match.group()) if match else None

    @staticmethod
    def _split_references(text: str) -> tuple[str, str]:
        """Split markdown text into body and references section.

        Matches common formats:
        - Markdown headings: ## References, # Bibliography, etc.
        - Bold text on its own line: **References**
        - All-caps on its own line: REFERENCES
        Returns (body_text, references_text).
        """
        pattern = re.compile(
            r"^(?:#{1,3}\s+|\*\*)?(?:References|Bibliography|Works Cited|Literature Cited)(?:\*\*)?\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        match = pattern.search(text)
        if match:
            body = text[:match.start()].rstrip()
            references = text[match.start():]
            return body, references
        return text, ""
