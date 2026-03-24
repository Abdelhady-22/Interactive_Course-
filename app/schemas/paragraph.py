"""Pydantic schemas for Paragraph API requests and responses."""
import uuid

from pydantic import BaseModel, Field


class ParagraphCreate(BaseModel):
    """A single paragraph from the STT-aligned script."""
    text: str = Field(..., min_length=1)
    keywords: list[str] = Field(default_factory=list)
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)


class ParagraphBulkCreate(BaseModel):
    """Request body for importing all paragraphs at once (from STT JSON)."""
    paragraphs: list[ParagraphCreate]


class ParagraphResponse(BaseModel):
    """Response body for a paragraph."""
    id: uuid.UUID
    course_id: uuid.UUID
    order_index: int
    text: str
    keywords: list[str]
    start_ms: int
    end_ms: int
    has_decision: bool = False

    model_config = {"from_attributes": True}


class ParagraphListResponse(BaseModel):
    """Response body for listing paragraphs."""
    paragraphs: list[ParagraphResponse]
    total: int
