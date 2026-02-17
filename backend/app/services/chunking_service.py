from typing import List, Optional


class ChunkingService:
    """Service for chunking text into smaller pieces"""

    def __init__(self, chunk_size: int = 500, overlap: int = 100, mode: str = "characters"):
        """
        Args:
            chunk_size: Size of each chunk (in characters or tokens depending on mode)
            overlap: Overlap between chunks (in characters or tokens depending on mode)
            mode: "characters" or "tokens"
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.mode = mode
        self._tokenizer = None

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            from transformers import AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
        return self._tokenizer

    def chunk_text(self, text: str) -> List[str]:
        """
        Chunk text using fixed-size strategy with overlap.

        Uses character-based or token-based chunking depending on self.mode.
        """
        if self.mode == "tokens":
            return self._chunk_by_tokens(text)
        return self._chunk_by_characters(text)

    def _chunk_by_characters(self, text: str) -> List[str]:
        """Chunk text by character count with overlap."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)

            start += (self.chunk_size - self.overlap)

            if end >= len(text):
                break

        return chunks

    def _chunk_by_tokens(self, text: str) -> List[str]:
        """Chunk text by token count with overlap, returning text strings."""
        token_ids = self.tokenizer.encode(text, add_special_tokens=False)

        if len(token_ids) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        step = self.chunk_size - self.overlap

        while start < len(token_ids):
            end = min(start + self.chunk_size, len(token_ids))
            chunk_ids = token_ids[start:end]
            chunk_text = self.tokenizer.decode(chunk_ids, skip_special_tokens=True)
            chunks.append(chunk_text)

            if end >= len(token_ids):
                break
            start += step

        return chunks

    def chunk_by_paragraphs(self, text: str) -> List[str]:
        """
        Chunk text by paragraph boundaries (for future use).
        """
        paragraphs = text.split('\n\n')
        return [p.strip() for p in paragraphs if p.strip()]
