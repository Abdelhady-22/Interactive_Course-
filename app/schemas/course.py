"""Pydantic schemas for Course API requests and responses."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.course import CourseStatus


class CourseCreate(BaseModel):
    """Request body for creating a course."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    video_description: str | None = Field(
        None,
        description="Text description of the video (sent to LLM instead of video file)"
    )


class CourseUpdate(BaseModel):
    """Request body for updating a course."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    video_description: str | None = None


class CourseResponse(BaseModel):
    """Response body for a course."""
    id: uuid.UUID
    title: str
    description: str | None
    video_filename: str | None
    video_description: str | None
    status: CourseStatus
    paragraph_count: int = 0
    asset_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CourseListResponse(BaseModel):
    """Response body for listing courses."""
    courses: list[CourseResponse]
    total: int
