"""Course service — business logic for course management."""
import uuid

from sqlalchemy.orm import Session

from app.models.course import Course, CourseStatus
from app.models.paragraph import Paragraph
from app.models.asset import Asset
from app.schemas.course import CourseCreate, CourseUpdate


def create_course(db: Session, data: CourseCreate) -> Course:
    """Create a new course."""
    course = Course(
        title=data.title,
        description=data.description,
        video_description=data.video_description,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def get_course(db: Session, course_id: uuid.UUID) -> Course | None:
    """Get a single course by ID."""
    return db.query(Course).filter(Course.id == course_id).first()


def list_courses(db: Session) -> list[Course]:
    """List all courses."""
    return db.query(Course).order_by(Course.created_at.desc()).all()


def update_course(db: Session, course_id: uuid.UUID, data: CourseUpdate) -> Course | None:
    """Update a course's metadata."""
    course = get_course(db, course_id)
    if not course:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(course, field, value)

    db.commit()
    db.refresh(course)
    return course


def set_course_status(db: Session, course_id: uuid.UUID, status: CourseStatus) -> Course | None:
    """Update a course's status."""
    course = get_course(db, course_id)
    if not course:
        return None
    course.status = status
    db.commit()
    db.refresh(course)
    return course


def get_paragraph_count(db: Session, course_id: uuid.UUID) -> int:
    """Get the number of paragraphs in a course."""
    return db.query(Paragraph).filter(Paragraph.course_id == course_id).count()


def get_asset_count(db: Session, course_id: uuid.UUID) -> int:
    """Get the number of assets in a course."""
    return db.query(Asset).filter(Asset.course_id == course_id).count()
