"""Seed the database with the LLM test course (no assets).

Usage:
    python -m mock_data.seed_llm_test
"""
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import SessionLocal, engine, Base
from app.models import Course, Paragraph, Asset
from app.models.asset import AssetType
from app.models.course import CourseStatus


def seed():
    """Load sample_course_llm_test.json and populate the database."""
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Load mock data
    data_path = Path(__file__).parent / "sample_course_llm_test.json"
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()

    try:
        # Create course
        course_data = data["course"]
        course = Course(
            title=course_data["title"],
            description=course_data["description"],
            video_description=course_data["video_description"],
            status=CourseStatus.DRAFT,
        )
        db.add(course)
        db.flush()

        print(f"Created course: {course.title} (ID: {course.id})")

        # Create paragraphs
        for idx, p_data in enumerate(data["paragraphs"]):
            paragraph = Paragraph(
                course_id=course.id,
                order_index=idx,
                text=p_data["text"],
                keywords=p_data["keywords"],
                start_ms=p_data["start_ms"],
                end_ms=p_data["end_ms"],
            )
            db.add(paragraph)
            print(f"  Paragraph {idx}: {p_data['text'][:60]}...")

        # Create assets (empty for this test)
        for a_data in data.get("assets", []):
            asset = Asset(
                course_id=course.id,
                type=AssetType(a_data["type"]),
                name=a_data["name"],
                description=a_data["description"],
                content=a_data.get("content"),
            )
            db.add(asset)
            print(f"  Asset: {a_data['name']} ({a_data['type']})")

        db.commit()
        print(f"\nSeeding complete!")
        print(f"  Course ID: {course.id}")
        print(f"  Paragraphs: {len(data['paragraphs'])}")
        print(f"  Assets: {len(data.get('assets', []))}")
        print(f"\nThis course has NO assets — all paragraphs will go to CrewAI/LLM.")
        print(f"  Paragraphs 1 and 9 have intro/summary keywords → rules (instructor_only)")
        print(f"  Paragraphs 2-8 have no rule matches → CrewAI/Groq LLM")
        print(f"\nNext step: Run the agent with:")
        print(f"  POST http://localhost:8000/api/courses/{course.id}/process")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
