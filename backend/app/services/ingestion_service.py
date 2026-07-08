import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.models.paper import Chunk, ChunkType
from app.services.chunking_service import ChunkingService, classify_heading
from app.services.ollama_service import OllamaService
from app.services.qdrant_service import QdrantService
from app.services.sparse_embedding_service import SparseEmbeddingService

_PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")


class IngestionService:
    """Service for ingesting preprocessed markdown files into a collection."""

    def __init__(
        self,
        chunking_service: ChunkingService,
        ollama_service: OllamaService,
        qdrant_service: QdrantService,
        sparse_embedding_service: SparseEmbeddingService | None = None,
        max_tokens: int | None = None,
    ):
        self.chunking_service = chunking_service
        self.ollama_service = ollama_service
        self.qdrant_service = qdrant_service
        self.sparse_embedding_service = sparse_embedding_service
        self.max_tokens = max_tokens
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
            files.append(
                {
                    "markdown_file": md_file.name,
                    "has_metadata": metadata_path.exists(),
                    "stem": stem,
                }
            )

        # Count total PDFs in the corresponding pdf_input directory
        dir_name = preprocessed_path.name
        pdf_input_dir = Path(settings.pdf_input_dir) / dir_name
        total_pdfs = (
            len(list(pdf_input_dir.glob("*.pdf"))) if pdf_input_dir.is_dir() else 0
        )

        return {"files": files, "total_pdfs": total_pdfs}

    def create_collection(
        self,
        collection_id: str,
        name: str,
        description: str | None = None,
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
            collection_id,
            vector_size=vector_size,
            search_type=search_type,
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
        metadata_path: str | None = None,
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

        # Build unique_id from metadata
        unique_id = self._generate_unique_id(
            title=metadata.get("title", md_file.stem),
            authors=metadata.get("authors", []),
            year=self._extract_year(metadata.get("publication_date")),
        )

        # Use unique_id as paper_id; handle collisions by appending _2, _3, …
        collection_meta_dir = self.data_dir / collection_id / "metadata"
        collection_meta_dir.mkdir(parents=True, exist_ok=True)
        paper_id = unique_id
        _candidate = collection_meta_dir / f"{paper_id}.json"
        _counter = 2
        while _candidate.exists():
            paper_id = f"{unique_id}_{_counter}"
            _candidate = collection_meta_dir / f"{paper_id}.json"
            _counter += 1

        # Strip references section before chunking
        body_text, references = self._split_references(text_content)

        # Chunk text (body only, no references)
        chunks = []
        if self.chunking_service.mode == "markdown-academic":
            chunk_pairs = self.chunking_service.chunk_markdown(body_text)
            for i, (chunk_text, section_heading) in enumerate(chunk_pairs):
                chunk = Chunk(
                    paper_id=paper_id,
                    unique_id=unique_id,
                    chunk_text=chunk_text,
                    chunk_type=classify_heading(section_heading),
                    page_number="1",
                    metadata={"chunk_index": i, "section_heading": section_heading},
                )
                chunks.append(chunk)
        else:
            for i, chunk_text in enumerate(self.chunking_service.chunk_text(body_text)):
                chunk = Chunk(
                    paper_id=paper_id,
                    unique_id=unique_id,
                    chunk_text=chunk_text,
                    chunk_type=ChunkType.BODY,
                    page_number="1",
                    metadata={"chunk_index": i, "section_heading": ""},
                )
                chunks.append(chunk)

        # Resolve page numbers from embedded markers and strip them from chunk text
        chunks = [
            c.model_copy(
                update={
                    "page_number": self._extract_page_range(c.chunk_text),
                    "chunk_text": _PAGE_MARKER_RE.sub("", c.chunk_text).strip(),
                }
            )
            for c in chunks
        ]

        # Safety-cap for character/markdown modes: truncate any chunk that exceeds
        # the embedding context window. Skipped for token mode because chunk_size
        # is already capped to safe_max at service-creation time.
        if self.max_tokens is not None and self.chunking_service.mode != "tokens":
            chunks = [
                chunk.model_copy(
                    update={
                        "chunk_text": self.chunking_service.truncate_to_tokens(
                            chunk.chunk_text, self.max_tokens
                        )
                    }
                )
                for chunk in chunks
            ]

        # Generate embeddings
        chunk_texts = [c.chunk_text for c in chunks]
        embeddings = self.ollama_service.generate_embeddings_batch(chunk_texts)

        # Generate sparse embeddings for hybrid collections
        sparse_vectors = None
        if self._is_hybrid_collection(collection_id) and self.sparse_embedding_service:
            sparse_vectors = (
                self.sparse_embedding_service.generate_sparse_embeddings_batch(
                    chunk_texts
                )
            )

        # Store in Qdrant
        self.qdrant_service.upsert_chunks(
            collection_name=collection_id,
            chunks=chunks,
            vectors=embeddings,
            sparse_vectors=sparse_vectors,
        )

        # Copy metadata JSON to collection's metadata/ dir (_candidate already resolved above)
        paper_meta = {
            **metadata,
            "paper_id": paper_id,
            "unique_id": unique_id,
            "preprocessed_dir": md_file.parent.name,
            "source_pdf": metadata.get("source_pdf") or f"{md_file.stem}.pdf",
            "sections": self._extract_headings(body_text),
            "chunks_created": len(chunks),
            "references": references,
            "ingested_at": datetime.now(UTC).isoformat(),
        }
        _candidate.write_text(json.dumps(paper_meta, indent=2), encoding="utf-8")

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
        year: int | None,
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

    def _extract_year(self, publication_date: str | None) -> int | None:
        """Extract year from a publication date string."""
        if not publication_date:
            return None
        match = re.search(r"\d{4}", str(publication_date))
        return int(match.group()) if match else None

    @staticmethod
    def _extract_page_range(text: str) -> str:
        """Return 'N' or 'N-M' from <!-- page: N --> markers embedded in text."""
        pages = [int(m) for m in _PAGE_MARKER_RE.findall(text)]
        if not pages:
            return "1"
        lo, hi = min(pages), max(pages)
        return str(lo) if lo == hi else f"{lo}-{hi}"

    @staticmethod
    def _extract_headings(text: str) -> list[str]:
        """Extract H1/H2 heading titles from markdown text."""
        pattern = re.compile(r"^#{1,2} (.+)$", re.MULTILINE)
        return [m.group(1).strip() for m in pattern.finditer(text)]

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
            r"^(?:#{1,3}\s+)?(?:\*\*)?(?:References|Bibliography|Works Cited|Literature Cited)(?:\*\*)?\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        match = pattern.search(text)
        if match:
            body = text[: match.start()].rstrip()
            references = text[match.start() :]
            return body, references
        return text, ""
