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
