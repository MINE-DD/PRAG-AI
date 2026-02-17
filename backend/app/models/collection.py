from datetime import datetime, UTC
from typing import Optional
from pydantic import BaseModel, Field


class Collection(BaseModel):
    """Collection of research papers"""
    collection_id: str = Field(..., description="Unique collection identifier")
    name: str = Field(..., description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    created_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    paper_count: int = Field(default=0, description="Number of papers")
    search_type: str = Field(default="dense", description="Search type: dense or hybrid")


class CollectionResponse(BaseModel):
    """Response model for collection with papers"""
    collection_id: str
    name: str
    papers: list[dict] = Field(default_factory=list)
