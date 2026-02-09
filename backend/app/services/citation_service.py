from typing import Optional
from app.models.paper import PaperMetadata


class CitationService:
    """Service for formatting academic citations"""

    def format_apa(self, metadata: PaperMetadata) -> str:
        """
        Format paper metadata as APA citation.

        Example: Vaswani, A., Shazeer, N., et al. (2017). Attention Is All You Need. NeurIPS.
        """
        parts = []

        # Authors
        if metadata.authors:
            authors = self.format_authors_apa(metadata.authors)
            parts.append(authors)

        # Year
        if metadata.year:
            parts.append(f"({metadata.year})")

        # Title (italicized in actual formatting)
        parts.append(metadata.title)

        # Journal/Conference
        if metadata.journal_conference:
            parts.append(metadata.journal_conference)

        return ". ".join(parts) + "."

    def format_bibtex(self, metadata: PaperMetadata) -> str:
        """
        Format paper metadata as BibTeX entry.

        Example:
        @article{VaswaniAttention2017,
          title = {Attention Is All You Need},
          author = {Vaswani, A. and Shazeer, N.},
          year = {2017}
        }
        """
        key = self.extract_citation_key(metadata)
        lines = [f"@article{{{key},"]

        # Title
        lines.append(f"  title = {{{metadata.title}}},")

        # Authors
        if metadata.authors:
            authors = self.format_authors_bibtex(metadata.authors)
            lines.append(f"  author = {{{authors}}},")

        # Year
        if metadata.year:
            lines.append(f"  year = {{{metadata.year}}},")

        # Journal/Conference
        if metadata.journal_conference:
            lines.append(f"  journal = {{{metadata.journal_conference}}},")

        # Remove trailing comma from last line
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]

        lines.append("}")
        return "\n".join(lines)

    def extract_citation_key(self, metadata: PaperMetadata) -> str:
        """Extract BibTeX citation key (use unique_id)"""
        return metadata.unique_id

    def format_authors_apa(self, authors: list[str]) -> str:
        """
        Format author list for APA style.

        - 1 author: Smith, J.
        - 2 authors: Smith, J., & Doe, A.
        - 3-20 authors: List all with & before last
        - 21+ authors: First 19, ..., last author
        """
        if not authors:
            return ""

        if len(authors) == 1:
            return authors[0]

        if len(authors) == 2:
            return f"{authors[0]}, & {authors[1]}"

        # For 3-20 authors, list all
        if len(authors) <= 20:
            all_but_last = ", ".join(authors[:-1])
            return f"{all_but_last}, & {authors[-1]}"

        # For 21+ authors (rare), use ellipsis
        first_19 = ", ".join(authors[:19])
        return f"{first_19}, ... {authors[-1]}"

    def format_authors_bibtex(self, authors: list[str]) -> str:
        """
        Format author list for BibTeX (separated by 'and').

        Example: Smith, J. and Doe, A. and Johnson, B.
        """
        if not authors:
            return ""

        return " and ".join(authors)
