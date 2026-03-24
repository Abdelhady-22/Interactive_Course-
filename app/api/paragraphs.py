"""Paragraph API endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.paragraph import Paragraph
from app.services.course_service import get_course
from app.schemas.paragraph import (
    ParagraphBulkCreate,
    ParagraphListResponse,
    ParagraphResponse,
)

router = APIRouter(prefix="/api/courses/{course_id}/paragraphs", tags=["Paragraphs"])


def _to_response(p: Paragraph) -> ParagraphResponse:
    """Convert a Paragraph model to ParagraphResponse."""
    return ParagraphResponse(
        id=p.id,
        course_id=p.course_id,
        order_index=p.order_index,
        text=p.text,
        keywords=p.keywords or [],
        start_ms=p.start_ms,
        end_ms=p.end_ms,
        has_decision=p.decision is not None,
    )


@router.post("/", response_model=ParagraphListResponse, status_code=201)
def bulk_import_paragraphs(
    course_id: uuid.UUID,
    data: ParagraphBulkCreate,
    db: Session = Depends(get_db),
):
    """Bulk import paragraphs from STT-aligned JSON.

    Replaces all existing paragraphs for this course.
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Delete existing paragraphs (load objects to trigger ORM cascade for decisions)
    existing_paragraphs = (
        db.query(Paragraph)
        .options(joinedload(Paragraph.decision))
        .filter(Paragraph.course_id == course_id)
        .all()
    )
    for ep in existing_paragraphs:
        db.delete(ep)
    db.flush()

    # Create new paragraphs in order
    created = []
    for idx, p in enumerate(data.paragraphs):
        paragraph = Paragraph(
            course_id=course_id,
            order_index=idx,
            text=p.text,
            keywords=p.keywords,
            start_ms=p.start_ms,
            end_ms=p.end_ms,
        )
        db.add(paragraph)
        created.append(paragraph)

    db.commit()
    for p in created:
        db.refresh(p)

    return ParagraphListResponse(
        paragraphs=[_to_response(p) for p in created],
        total=len(created),
    )


@router.get("/", response_model=ParagraphListResponse)
def list_paragraphs(course_id: uuid.UUID, db: Session = Depends(get_db)):
    """List all paragraphs for a course, ordered by position."""
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.course_id == course_id)
        .order_by(Paragraph.order_index)
        .all()
    )

    return ParagraphListResponse(
        paragraphs=[_to_response(p) for p in paragraphs],
        total=len(paragraphs),
    )
