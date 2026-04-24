from enum import Enum

from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    """Types of document chunks"""

    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    RELATED_WORK = "related_work"
    METHODS = "methods"
    DATA = "data"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    ACKNOWLEDGEMENTS = "acknowledgements"
    APPENDIX = "appendix"
    BODY = "body"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"


class PaperMetadata(BaseModel):
    """Metadata for a document (paper, invoice, report, or any other type)."""

    paper_id: str = Field(..., description="Unique document identifier")
    title: str = Field(..., description="Document title")
    authors: list[str] = Field(default_factory=list, description="Authors or creators")
    year: int | None = Field(None, description="Publication or creation year")
    abstract: str | None = Field(None, description="Abstract or summary")
    keywords: list[str] = Field(default_factory=list, description="Keywords")
    journal_conference: str | None = Field(None, description="Publication venue")
    citations: list[str] = Field(default_factory=list, description="Cited papers")
    unique_id: str = Field(..., description="Human-readable citation ID")
    pdf_path: str | None = Field(None, description="Path to PDF file")
    figures: list[dict] = Field(default_factory=list, description="Figure metadata")
    publication_date: str | None = Field(None, description="Publication date")
    extra_metadata: dict = Field(
        default_factory=dict,
        description="Document-type-specific fields (e.g. vendor, invoice_number for invoices)",
    )


class Chunk(BaseModel):
    """Document chunk for embedding"""

    paper_id: str = Field(..., description="Paper this chunk belongs to")
    unique_id: str = Field(..., description="Human-readable citation ID")
    chunk_text: str = Field(..., description="Chunk content")
    chunk_type: ChunkType = Field(..., description="Type of chunk")
    page_number: int = Field(..., description="Source page number")
    metadata: dict | None = Field(None, description="Additional metadata")
