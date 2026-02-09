from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    """Types of document chunks"""
    ABSTRACT = "abstract"
    BODY = "body"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"


class PaperMetadata(BaseModel):
    """Metadata for a research paper"""
    paper_id: str = Field(..., description="Unique paper identifier")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="List of authors")
    year: Optional[int] = Field(None, description="Publication year")
    abstract: Optional[str] = Field(None, description="Paper abstract")
    keywords: list[str] = Field(default_factory=list, description="Keywords")
    journal_conference: Optional[str] = Field(None, description="Publication venue")
    citations: list[str] = Field(default_factory=list, description="Cited papers")
    unique_id: str = Field(..., description="Human-readable citation ID")
    pdf_path: Optional[str] = Field(None, description="Path to PDF file")
    figures: list[dict] = Field(default_factory=list, description="Figure metadata")
    publication_date: Optional[str] = Field(None, description="Publication date")


class Chunk(BaseModel):
    """Document chunk for embedding"""
    paper_id: str = Field(..., description="Paper this chunk belongs to")
    unique_id: str = Field(..., description="Human-readable citation ID")
    chunk_text: str = Field(..., description="Chunk content")
    chunk_type: ChunkType = Field(..., description="Type of chunk")
    page_number: int = Field(..., description="Source page number")
    metadata: Optional[dict] = Field(None, description="Additional metadata")
