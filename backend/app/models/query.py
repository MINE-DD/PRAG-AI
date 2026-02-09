from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request for querying papers"""
    collection_id: str = Field(..., description="Collection to query")
    paper_ids: list[str] = Field(default_factory=list, description="Paper IDs to search (empty = all)")
    query_text: str = Field(..., description="User question")
    chat_history: list[dict] = Field(default_factory=list, description="Previous messages")


class Source(BaseModel):
    """Citation source information"""
    unique_id: str = Field(..., description="Human-readable ID")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(..., description="Paper authors")
    year: Optional[int] = Field(None, description="Publication year")
    excerpts: list[str] = Field(default_factory=list, description="Relevant excerpts")
    pages: list[int] = Field(default_factory=list, description="Page numbers")


class QueryResponse(BaseModel):
    """Response from query operation"""
    answer: str = Field(..., description="Generated answer with citations")
    sources: list[Source] = Field(default_factory=list, description="Cited sources")
    cited_paper_ids: list[str] = Field(default_factory=list, description="Papers cited in answer")


class SummarizeRequest(BaseModel):
    """Request to summarize a paper"""
    collection_id: str
    paper_id: str
    chat_history: list[dict] = Field(default_factory=list)


class CompareRequest(BaseModel):
    """Request to compare papers"""
    collection_id: str
    paper_ids: list[str] = Field(..., min_length=2)
    aspect: str = Field(default="all", pattern="^(methodology|findings|all)$")
    chat_history: list[dict] = Field(default_factory=list)
