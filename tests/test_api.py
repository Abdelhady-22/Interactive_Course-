"""API endpoint tests using FastAPI TestClient.

These tests use an in-memory SQLite database for speed.
They test the full API flow: create course → add paragraphs → add assets → get decisions.

Note: Agent processing tests require an LLM and are skipped by default.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


# --- Test database setup (SQLite in-memory) ---

SQLALCHEMY_TEST_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# --- Helper ---

def create_test_course() -> dict:
    """Create a course and return the response."""
    response = client.post("/api/courses/", json={
        "title": "Test Chemistry Course",
        "description": "A test course",
        "video_description": "Instructor speaking to camera about chemistry",
    })
    assert response.status_code == 201
    return response.json()


def add_test_paragraphs(course_id: str) -> dict:
    """Add sample paragraphs to a course."""
    response = client.post(f"/api/courses/{course_id}/paragraphs/", json={
        "paragraphs": [
            {
                "text": "Welcome to this chemistry course.",
                "keywords": ["welcome", "introduction"],
                "start_ms": 0,
                "end_ms": 15000,
            },
            {
                "text": "The reaction of zinc with hydrochloric acid produces hydrogen gas.",
                "keywords": ["zinc", "hydrochloric acid", "reaction"],
                "start_ms": 15500,
                "end_ms": 40000,
            },
            {
                "text": "Let's summarize what we learned today.",
                "keywords": ["summary", "recap"],
                "start_ms": 40500,
                "end_ms": 55000,
            },
        ],
    })
    assert response.status_code == 201
    return response.json()


# --- Course Tests ---

class TestCourseAPI:
    def test_create_course(self):
        course = create_test_course()
        assert course["title"] == "Test Chemistry Course"
        assert course["status"] == "draft"
        assert course["paragraph_count"] == 0

    def test_list_courses(self):
        create_test_course()
        response = client.get("/api/courses/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    def test_get_course(self):
        course = create_test_course()
        response = client.get(f"/api/courses/{course['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == course["id"]

    def test_get_nonexistent_course(self):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/courses/{fake_id}")
        assert response.status_code == 404

    def test_update_course(self):
        course = create_test_course()
        response = client.patch(f"/api/courses/{course['id']}", json={
            "title": "Updated Title",
        })
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"


# --- Paragraph Tests ---

class TestParagraphAPI:
    def test_bulk_import_paragraphs(self):
        course = create_test_course()
        result = add_test_paragraphs(course["id"])
        assert result["total"] == 3
        assert result["paragraphs"][0]["order_index"] == 0
        assert result["paragraphs"][2]["order_index"] == 2

    def test_list_paragraphs(self):
        course = create_test_course()
        add_test_paragraphs(course["id"])

        response = client.get(f"/api/courses/{course['id']}/paragraphs/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_reimport_replaces_paragraphs(self):
        course = create_test_course()
        add_test_paragraphs(course["id"])

        # Import again with different data
        response = client.post(f"/api/courses/{course['id']}/paragraphs/", json={
            "paragraphs": [
                {"text": "Only one paragraph now.", "keywords": ["test"], "start_ms": 0, "end_ms": 5000},
            ],
        })
        assert response.status_code == 201
        assert response.json()["total"] == 1


# --- Asset Tests ---

class TestAssetAPI:
    def test_bulk_create_assets(self):
        course = create_test_course()
        response = client.post(f"/api/courses/{course['id']}/assets/bulk", json={
            "assets": [
                {"type": "formula", "name": "Test formula", "description": "A test formula", "content": "E=mc²"},
                {"type": "image", "name": "Test image", "description": "A test image"},
            ],
        })
        assert response.status_code == 201
        assert response.json()["total"] == 2

    def test_list_assets(self):
        course = create_test_course()
        client.post(f"/api/courses/{course['id']}/assets/bulk", json={
            "assets": [
                {"type": "chart", "name": "Test chart", "description": "A chart"},
            ],
        })
        response = client.get(f"/api/courses/{course['id']}/assets/")
        assert response.status_code == 200
        assert response.json()["total"] == 1


# --- Decision Tests (no LLM needed — tests rule-based decisions) ---

class TestDecisionAPI:
    def test_get_decisions_empty(self):
        course = create_test_course()
        response = client.get(f"/api/courses/{course['id']}/decisions")
        assert response.status_code == 200
        assert response.json()["total"] == 0


# --- Health Check ---

class TestHealth:
    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
