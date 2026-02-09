from pathlib import Path
from typing import Optional
from app.models.paper import Chunk, ChunkType, PaperMetadata
from app.services.pdf_processor import PDFProcessor
from app.services.chunking_service import ChunkingService
from app.services.ollama_service import OllamaService
from app.services.qdrant_service import QdrantService


class PaperService:
    """Service for processing papers through the full pipeline"""

    def __init__(
        self,
        pdf_processor: PDFProcessor,
        chunking_service: ChunkingService,
        ollama_service: OllamaService,
        qdrant_service: QdrantService
    ):
        self.pdf_processor = pdf_processor
        self.chunking_service = chunking_service
        self.ollama_service = ollama_service
        self.qdrant_service = qdrant_service

    def process_paper(
        self,
        collection_id: str,
        paper_id: str,
        pdf_path: Path
    ) -> dict:
        """
        Process a paper through the complete pipeline.

        Steps:
        1. Extract text and metadata from PDF
        2. Chunk the text
        3. Create Chunk objects with metadata
        4. Generate embeddings for chunks
        5. Store chunks and embeddings in Qdrant

        Args:
            collection_id: Collection this paper belongs to
            paper_id: Unique paper identifier
            pdf_path: Path to PDF file

        Returns:
            Dictionary with processing results
        """
        # Step 1: Extract text and metadata from PDF
        pdf_result = self.pdf_processor.process_pdf(pdf_path, paper_id)
        metadata: PaperMetadata = pdf_result["metadata"]
        text_content = pdf_result["text"]

        # Step 2: Chunk the text
        text_chunks = self.chunking_service.chunk_text(text_content)

        # Step 3: Create Chunk objects with metadata
        chunks = []
        for i, chunk_text in enumerate(text_chunks):
            chunk = Chunk(
                paper_id=paper_id,
                unique_id=metadata.unique_id,
                chunk_text=chunk_text,
                chunk_type=ChunkType.BODY,  # For now, all chunks are BODY type
                page_number=1,  # TODO: Track page numbers in future
                metadata={"chunk_index": i}
            )
            chunks.append(chunk)

        # Step 4: Generate embeddings for chunks
        chunk_texts = [chunk.chunk_text for chunk in chunks]
        embeddings = self.ollama_service.generate_embeddings(chunk_texts)

        # Step 5: Store chunks and embeddings in Qdrant
        self.qdrant_service.upsert_chunks(
            collection_name=collection_id,
            chunks=chunks,
            vectors=embeddings
        )

        return {
            "metadata": metadata,
            "chunks_created": len(chunks),
            "embeddings_generated": len(embeddings)
        }

    def delete_paper(self, collection_id: str, paper_id: str):
        """
        Delete a paper and all its chunks from Qdrant.

        Args:
            collection_id: Collection the paper belongs to
            paper_id: Paper identifier to delete
        """
        self.qdrant_service.delete_by_paper_id(collection_id, paper_id)
