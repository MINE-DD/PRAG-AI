from __future__ import annotations

import re


class ChunkingService:
    """Service for chunking text into smaller pieces"""

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 100,
        mode: str = "characters",
        min_chunk_size: int = 50,
    ):
        """
        Args:
            chunk_size: Max size of each chunk (characters or tokens depending on mode).
            overlap: Overlap between overflow-split chunks (same unit as chunk_size).
            mode: "characters", "tokens", or "markdown".
            min_chunk_size: Minimum chunk size in characters; smaller paragraphs are
                merged with the next one (markdown mode only).
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.mode = mode
        self.min_chunk_size = min_chunk_size
        self._tokenizer = None

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
        return self._tokenizer

    def chunk_text(self, text: str) -> list[str]:
        """Chunk text using the configured strategy."""
        if self.mode == "tokens":
            return self._chunk_by_tokens(text)
        if self.mode == "markdown":
            return [c for c, _ in self.chunk_markdown(text)]
        return self._chunk_by_characters(text)

    def chunk_markdown(self, text: str) -> list[tuple[str, str]]:
        """Markdown-aware hierarchical chunking.

        Returns a list of (chunk_text, section_heading) pairs. chunk_text always
        starts with the section heading so it is self-contained for retrieval.
        section_heading is stored separately as Qdrant payload for filtering.

        Strategy:
        1. Split on # / ## / ### headers → sections with inherited heading path.
        2. Within each section split on blank lines → paragraphs.
        3. Merge consecutive paragraphs that are below min_chunk_size.
        4. Overflow-split paragraphs that still exceed chunk_size using the
           character-based splitter (with overlap).
        """
        sections = self._split_by_headers(text)
        results: list[tuple[str, str]] = []

        for heading, body in sections:
            paragraphs = self._split_paragraphs(body)
            paragraphs = self._merge_short(paragraphs)

            for para in paragraphs:
                if len(para) <= self.chunk_size:
                    results.append((para, heading))
                else:
                    for sub in self._chunk_by_characters(para):
                        results.append((sub, heading))

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split_by_headers(self, text: str) -> list[tuple[str, str]]:
        """Split markdown into (heading_path, body) sections.

        Heading path is the concatenation of the most recent ## / ### headings,
        e.g. "## Background > ### Detail".  The first heading (paper title,
        regardless of level) is always excluded from heading paths.  Text
        before the first header is emitted with an empty heading.
        """
        header_re = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
        sections: list[tuple[str, str]] = []

        # Track the current heading at each level (h1, h2, h3)
        current_levels: dict[int, str] = {}
        # The very first heading in the document is the paper title — always excluded
        title_heading: str | None = None

        pos = 0
        preamble_end = None

        for m in header_re.finditer(text):
            heading_text = m.group(0).strip()
            if title_heading is None:
                title_heading = heading_text

            if preamble_end is None:
                # Emit preamble (text before first header)
                preamble = text[: m.start()].strip()
                if preamble:
                    sections.append(("", preamble))
                preamble_end = m.start()
            else:
                # Emit the previous section's body
                body = text[pos : m.start()].strip()
                # Remove the header line itself from body
                body = header_re.sub("", body, count=0).strip()
                if body:
                    sections.append(
                        (_build_heading_path(current_levels, title_heading), body)
                    )

            level = len(m.group(1))
            # Update heading at this level and clear deeper levels
            current_levels[level] = heading_text
            for deeper in list(current_levels):
                if deeper > level:
                    del current_levels[deeper]

            pos = m.end()

        # Emit the last section
        if preamble_end is not None:
            body = text[pos:].strip()
            body = header_re.sub("", body, count=0).strip()
            if body:
                sections.append(
                    (_build_heading_path(current_levels, title_heading), body)
                )
        elif not sections:
            # No headers at all — treat whole text as one section
            if text.strip():
                sections.append(("", text.strip()))

        return sections

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split on blank lines, strip each paragraph."""
        return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    def _merge_short(self, paragraphs: list[str]) -> list[str]:
        """Merge consecutive paragraphs that are below min_chunk_size."""
        merged: list[str] = []
        buf = ""
        for para in paragraphs:
            if not buf:
                buf = para
            elif len(buf) < self.min_chunk_size:
                buf = f"{buf}\n\n{para}"
            else:
                merged.append(buf)
                buf = para
        if buf:
            merged.append(buf)
        return merged

    def _chunk_by_characters(
        self, text: str, chunk_size: int | None = None
    ) -> list[str]:
        """Chunk text by character count with overlap."""
        size = chunk_size if chunk_size is not None else self.chunk_size
        if len(text) <= size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + size
            chunks.append(text[start:end])
            if end >= len(text):
                break
            start += size - self.overlap
        return chunks

    def _chunk_by_tokens(self, text: str) -> list[str]:
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

    def chunk_by_paragraphs(self, text: str) -> list[str]:
        """Simple paragraph splitting (kept for backwards compatibility)."""
        paragraphs = text.split("\n\n")
        return [p.strip() for p in paragraphs if p.strip()]


def _build_heading_path(levels: dict[int, str], title: str | None = None) -> str:
    """Build a heading path string, excluding the paper title (first heading encountered)."""
    return " > ".join(v for _, v in sorted(levels.items()) if v != title)
