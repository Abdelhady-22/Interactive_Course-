"""Pydantic schemas for Asset API requests and responses."""
import uuid

from pydantic import BaseModel, Field

from app.models.asset import AssetType


class AssetCreate(BaseModel):
    """Request body for creating an asset (metadata only — file uploaded separately)."""
    type: AssetType
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    content: str | None = Field(
        None,
        description="Text content if applicable (formula text, axis labels, data labels, etc.)"
    )


class AssetResponse(BaseModel):
    """Response body for an asset."""
    id: uuid.UUID
    course_id: uuid.UUID
    type: AssetType
    name: str
    description: str
    content: str | None
    file_path: str | None

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    """Response body for listing assets."""
    assets: list[AssetResponse]
    total: int
