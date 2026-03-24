"""Asset API endpoints."""
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.asset import Asset, AssetType
from app.services.course_service import get_course
from app.schemas.asset import AssetListResponse, AssetResponse

router = APIRouter(prefix="/api/courses/{course_id}/assets", tags=["Assets"])


# --- Pydantic model for bulk asset creation ---

class BulkAssetItem(BaseModel):
    """A single asset in a bulk create request."""
    type: str
    name: str
    description: str
    content: str | None = None
    file_path: str | None = None


class BulkAssetRequest(BaseModel):
    """Request body for bulk asset creation."""
    assets: list[BulkAssetItem]


@router.post("/", response_model=AssetResponse, status_code=201)
async def upload_asset(
    course_id: uuid.UUID,
    type: AssetType = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    content: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Upload an asset with metadata.

    The file is optional — for formulas, the content field is what matters.
    For images/diagrams/charts, upload the file AND provide a description.
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    file_path = None
    if file:
        ext = file.filename.split(".")[-1] if file.filename else "png"
        filename = f"{course_id}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = settings.assets_dir / filename

        with open(filepath, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file_path = filename

    asset = Asset(
        course_id=course_id,
        type=type,
        name=name,
        description=description,
        content=content,
        file_path=file_path,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return AssetResponse.model_validate(asset)


@router.post("/bulk", response_model=AssetListResponse, status_code=201)
def bulk_create_assets(
    course_id: uuid.UUID,
    data: BulkAssetRequest,
    db: Session = Depends(get_db),
):
    """Bulk create assets from JSON (without file uploads).

    Useful for seeding assets with descriptions only.
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    created = []
    for a_data in data.assets:
        asset = Asset(
            course_id=course_id,
            type=AssetType(a_data.type),
            name=a_data.name,
            description=a_data.description,
            content=a_data.content,
            file_path=a_data.file_path,
        )
        db.add(asset)
        created.append(asset)

    db.commit()
    for a in created:
        db.refresh(a)

    return AssetListResponse(
        assets=[AssetResponse.model_validate(a) for a in created],
        total=len(created),
    )


@router.get("/", response_model=AssetListResponse)
def list_assets(course_id: uuid.UUID, db: Session = Depends(get_db)):
    """List all assets for a course."""
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    assets = db.query(Asset).filter(Asset.course_id == course_id).all()

    return AssetListResponse(
        assets=[AssetResponse.model_validate(a) for a in assets],
        total=len(assets),
    )


@router.delete("/{asset_id}", status_code=204)
def delete_asset(course_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a single asset."""
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.course_id == course_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()
