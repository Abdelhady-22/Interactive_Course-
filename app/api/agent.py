"""Agent / Decision API endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.decision import (
    DecisionListResponse,
    DecisionOverride,
    DecisionResponse,
    PlaybackData,
)
from app.services import agent_service
from app.services.course_service import get_course

router = APIRouter(prefix="/api", tags=["Agent & Decisions"])


@router.post("/courses/{course_id}/process", response_model=DecisionListResponse)
def process_course(
    course_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Run the AI agent on all paragraphs of a course.

    This is the main processing endpoint. It:
    1. Reads all paragraphs and assets for the course
    2. Runs the hybrid agent (rules first, then LLM) on each paragraph
    3. Stores all decisions
    4. Sets course status to 'reviewed'
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    try:
        decisions = agent_service.run_agent_on_course(db, course_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DecisionListResponse(
        course_id=course_id,
        decisions=[DecisionResponse.model_validate(d) for d in decisions],
        total=len(decisions),
        approved_count=sum(1 for d in decisions if d.is_approved),
    )


@router.get("/courses/{course_id}/decisions", response_model=DecisionListResponse)
def get_decisions(course_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get all decisions for a course, ordered by paragraph position."""
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    decisions = agent_service.get_decisions_for_course(db, course_id)

    return DecisionListResponse(
        course_id=course_id,
        decisions=[DecisionResponse.model_validate(d) for d in decisions],
        total=len(decisions),
        approved_count=sum(1 for d in decisions if d.is_approved),
    )


@router.put("/decisions/{decision_id}", response_model=DecisionResponse)
def override_decision(
    decision_id: uuid.UUID,
    override: DecisionOverride,
    db: Session = Depends(get_db),
):
    """Override a decision manually (human editor).

    Sets decided_by to 'human_override', confidence to 1.0,
    and auto-approves the decision.
    """
    try:
        decision = agent_service.override_decision(db, decision_id, override)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DecisionResponse.model_validate(decision)


@router.post("/decisions/{decision_id}/rerun", response_model=DecisionResponse)
def rerun_decision(
    decision_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Re-run the agent on a single paragraph.

    Useful when the editor wants a new suggestion from the agent.
    Resets approval status.
    """
    try:
        decision = agent_service.run_agent_on_paragraph(db, decision_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DecisionResponse.model_validate(decision)


@router.post("/decisions/{decision_id}/approve", response_model=DecisionResponse)
def approve_decision(decision_id: uuid.UUID, db: Session = Depends(get_db)):
    """Approve a single decision."""
    try:
        decision = agent_service.approve_decision(db, decision_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DecisionResponse.model_validate(decision)


@router.post("/courses/{course_id}/approve-all", response_model=DecisionListResponse)
def approve_all_decisions(course_id: uuid.UUID, db: Session = Depends(get_db)):
    """Approve all decisions for a course at once."""
    decisions = agent_service.get_decisions_for_course(db, course_id)
    if not decisions:
        raise HTTPException(status_code=404, detail="No decisions found for this course")

    for d in decisions:
        d.is_approved = True
    db.commit()

    return DecisionListResponse(
        course_id=course_id,
        decisions=[DecisionResponse.model_validate(d) for d in decisions],
        total=len(decisions),
        approved_count=len(decisions),
    )


@router.post("/courses/{course_id}/publish", response_model=dict)
def publish_course(course_id: uuid.UUID, db: Session = Depends(get_db)):
    """Publish a course. Requires all decisions to be approved."""
    try:
        course = agent_service.publish_course(db, course_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": f"Course '{course.title}' published successfully", "status": course.status.value}


@router.get("/courses/{course_id}/playback", response_model=PlaybackData)
def get_playback_data(course_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get the final playback JSON for the learner player.

    Returns the video filename and the ordered decision array.
    Only available for published courses.
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    decisions = agent_service.get_decisions_for_course(db, course_id)

    return PlaybackData(
        course_id=course.id,
        title=course.title,
        video_filename=course.video_filename,
        decisions=[DecisionResponse.model_validate(d) for d in decisions],
    )
