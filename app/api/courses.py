"""Course API endpoints."""
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.course import CourseCreate, CourseListResponse, CourseResponse, CourseUpdate
from app.services import course_service

router = APIRouter(prefix="/api/courses", tags=["Courses"])


def _to_response(course, db: Session) -> CourseResponse:
    """Convert a Course model to CourseResponse with counts."""
    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
        video_filename=course.video_filename,
        video_description=course.video_description,
        status=course.status,
        paragraph_count=course_service.get_paragraph_count(db, course.id),
        asset_count=course_service.get_asset_count(db, course.id),
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


@router.post("/", response_model=CourseResponse, status_code=201)
def create_course(data: CourseCreate, db: Session = Depends(get_db)):
    """Create a new course."""
    course = course_service.create_course(db, data)
    return _to_response(course, db)


@router.get("/", response_model=CourseListResponse)
def list_courses(db: Session = Depends(get_db)):
    """List all courses."""
    courses = course_service.list_courses(db)
    return CourseListResponse(
        courses=[_to_response(c, db) for c in courses],
        total=len(courses),
    )


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(course_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a single course."""
    course = course_service.get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _to_response(course, db)


@router.patch("/{course_id}", response_model=CourseResponse)
def update_course(course_id: uuid.UUID, data: CourseUpdate, db: Session = Depends(get_db)):
    """Update a course's metadata."""
    course = course_service.update_course(db, course_id, data)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _to_response(course, db)


@router.post("/{course_id}/upload-video", response_model=CourseResponse)
async def upload_video(course_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a video file for a course."""
    course = course_service.get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Validate file type
    allowed_extensions = {"mp4", "webm", "mov", "avi", "mkv"}
    ext = file.filename.split(".")[-1].lower() if file.filename else "mp4"
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '.{ext}'. Allowed: {', '.join(allowed_extensions)}"
        )

    # Validate file size (500MB max)
    max_size = 500 * 1024 * 1024  # 500MB
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(contents) // (1024*1024)}MB). Maximum: 500MB"
        )

    # Save video file
    filename = f"{course_id}.{ext}"
    filepath = settings.videos_dir / filename

    with open(filepath, "wb") as f:
        f.write(contents)

    course.video_filename = filename
    db.commit()
    db.refresh(course)

    return _to_response(course, db)
