"""Pydantic schemas for Paragraph API requests and responses."""
import uuid

from pydantic import BaseModel, Field, model_validator


class ParagraphCreate(BaseModel):
    """A single paragraph from the STT-aligned script."""
    text: str = Field(..., min_length=1)
    keywords: list[str] = Field(default_factory=list)
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_ms <= self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) must be greater than start_ms ({self.start_ms})")
        return self


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
