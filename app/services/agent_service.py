"""Agent service — business logic for running the agent and managing decisions."""
import logging
import uuid

from sqlalchemy.orm import Session

from app.agent.engine import process_paragraph, process_course
from app.models.asset import Asset
from app.models.course import Course, CourseStatus
from app.models.decision import Decision, DecisionSource
from app.models.paragraph import Paragraph
from app.schemas.decision import DecisionOutput, DecisionOverride

logger = logging.getLogger(__name__)


def _paragraph_to_dict(p: Paragraph) -> dict:
    """Convert a Paragraph model to the dict format the agent expects."""
    return {
        "id": str(p.id),
        "text": p.text,
        "keywords": p.keywords or [],
        "start_ms": p.start_ms,
        "end_ms": p.end_ms,
    }


def _asset_to_dict(a: Asset) -> dict:
    """Convert an Asset model to the dict format the agent expects."""
    return {
        "id": str(a.id),
        "type": a.type.value,
        "name": a.name,
        "description": a.description,
        "content": a.content,
    }


def _save_decision(db: Session, paragraph_id: uuid.UUID, decision: DecisionOutput) -> Decision:
    """Save or update a decision in the database."""
    # Check if decision already exists for this paragraph
    existing = db.query(Decision).filter(Decision.paragraph_id == paragraph_id).first()

    if existing:
        existing.layout = decision.layout.model_dump()
        existing.assets = [a.model_dump() for a in decision.assets]
        existing.transition = decision.transition.model_dump()
        existing.script_display = decision.script_display.model_dump()
        existing.continuity = decision.continuity.model_dump()
        existing.director_note = decision.director_note
        existing.confidence = decision.confidence
        existing.decided_by = decision.decided_by
        existing.is_approved = False  # Reset approval on re-run
        db.commit()
        db.refresh(existing)
        return existing
    else:
        db_decision = Decision(
            paragraph_id=paragraph_id,
            layout=decision.layout.model_dump(),
            assets=[a.model_dump() for a in decision.assets],
            transition=decision.transition.model_dump(),
            script_display=decision.script_display.model_dump(),
            continuity=decision.continuity.model_dump(),
            director_note=decision.director_note,
            confidence=decision.confidence,
            decided_by=decision.decided_by,
            is_approved=False,
        )
        db.add(db_decision)
        db.commit()
        db.refresh(db_decision)
        return db_decision


def run_agent_on_course(db: Session, course_id: uuid.UUID) -> list[Decision]:
    """Run the agent on all paragraphs of a course.

    Returns list of stored Decision objects.
    """
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise ValueError(f"Course {course_id} not found")

    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.course_id == course_id)
        .order_by(Paragraph.order_index)
        .all()
    )
    if not paragraphs:
        raise ValueError(f"Course {course_id} has no paragraphs")

    assets = db.query(Asset).filter(Asset.course_id == course_id).all()

    # Build video context
    video_context = {
        "description": course.video_description or "Educational course, instructor speaking to camera."
    }

    # Convert to dicts for the agent
    para_dicts = [_paragraph_to_dict(p) for p in paragraphs]
    asset_dicts = [_asset_to_dict(a) for a in assets]

    # Update course status
    course.status = CourseStatus.PROCESSING
    db.commit()

    # Run agent
    decisions = process_course(para_dicts, asset_dicts, video_context)

    # Save all decisions
    stored = []
    for p, d in zip(paragraphs, decisions):
        stored_decision = _save_decision(db, p.id, d)
        stored.append(stored_decision)

    # Update course status
    course.status = CourseStatus.REVIEWED
    db.commit()

    logger.info(f"Course {course_id}: processed {len(stored)} paragraphs")
    return stored


def run_agent_on_paragraph(
    db: Session,
    decision_id: uuid.UUID,
) -> Decision:
    """Re-run the agent on a single paragraph."""
    decision = db.query(Decision).filter(Decision.id == decision_id).first()
    if not decision:
        raise ValueError(f"Decision {decision_id} not found")

    paragraph = decision.paragraph
    course = paragraph.course

    assets = db.query(Asset).filter(Asset.course_id == course.id).all()

    video_context = {
        "description": course.video_description or "Educational course, instructor speaking to camera."
    }

    new_decision = process_paragraph(
        paragraph_id=str(paragraph.id),
        paragraph=_paragraph_to_dict(paragraph),
        assets=[_asset_to_dict(a) for a in assets],
        video_context=video_context,
    )

    stored = _save_decision(db, paragraph.id, new_decision)
    logger.info(f"Paragraph {paragraph.id}: re-processed → layout={new_decision.layout.mode}")
    return stored


def override_decision(
    db: Session,
    decision_id: uuid.UUID,
    override: DecisionOverride,
) -> Decision:
    """Apply a human override to a decision."""
    decision = db.query(Decision).filter(Decision.id == decision_id).first()
    if not decision:
        raise ValueError(f"Decision {decision_id} not found")

    if override.layout is not None:
        decision.layout = override.layout.model_dump()
    if override.assets is not None:
        decision.assets = [a.model_dump() for a in override.assets]
    if override.transition is not None:
        decision.transition = override.transition.model_dump()
    if override.script_display is not None:
        decision.script_display = override.script_display.model_dump()
    if override.continuity is not None:
        decision.continuity = override.continuity.model_dump()
    if override.director_note is not None:
        decision.director_note = override.director_note

    decision.decided_by = DecisionSource.HUMAN_OVERRIDE
    decision.confidence = 1.0
    decision.is_approved = True

    db.commit()
    db.refresh(decision)
    logger.info(f"Decision {decision_id}: human override applied")
    return decision


def approve_decision(db: Session, decision_id: uuid.UUID) -> Decision:
    """Approve a single decision."""
    decision = db.query(Decision).filter(Decision.id == decision_id).first()
    if not decision:
        raise ValueError(f"Decision {decision_id} not found")
    decision.is_approved = True
    db.commit()
    db.refresh(decision)
    return decision


def get_decisions_for_course(db: Session, course_id: uuid.UUID) -> list[Decision]:
    """Get all decisions for a course, ordered by paragraph."""
    return (
        db.query(Decision)
        .join(Paragraph)
        .filter(Paragraph.course_id == course_id)
        .order_by(Paragraph.order_index)
        .all()
    )


def publish_course(db: Session, course_id: uuid.UUID) -> Course:
    """Publish a course — requires all decisions to be approved."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise ValueError(f"Course {course_id} not found")

    decisions = get_decisions_for_course(db, course_id)
    paragraphs = db.query(Paragraph).filter(Paragraph.course_id == course_id).all()

    if len(decisions) != len(paragraphs):
        raise ValueError(
            f"Cannot publish: {len(paragraphs)} paragraphs but only {len(decisions)} decisions. Run agent first."
        )

    unapproved = [d for d in decisions if not d.is_approved]
    if unapproved:
        raise ValueError(
            f"Cannot publish: {len(unapproved)} decisions not yet approved."
        )

    course.status = CourseStatus.PUBLISHED
    db.commit()
    db.refresh(course)
    logger.info(f"Course {course_id}: published")
    return course
