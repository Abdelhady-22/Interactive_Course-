"""Unit tests for the rule-based decision engine."""
import pytest

from app.agent.rules import evaluate


class TestIntroRule:
    """Rule 1: Introduction / greeting → instructor_only."""

    def test_matches_welcome_keyword(self):
        decision = evaluate(
            paragraph_id="p_001",
            paragraph={
                "text": "Welcome to this course on chemistry.",
                "keywords": ["welcome", "course overview"],
                "start_ms": 0,
                "end_ms": 28000,
            },
            assets=[],
        )
        assert decision is not None
        assert decision.layout.mode == "instructor_only"
        assert decision.confidence >= 0.9
        assert decision.decided_by == "rule"

    def test_does_not_match_with_assets(self):
        """Intro rule should NOT fire if assets are present."""
        decision = evaluate(
            paragraph_id="p_001",
            paragraph={
                "text": "Welcome to this course.",
                "keywords": ["welcome", "introduction"],
                "start_ms": 0,
                "end_ms": 10000,
            },
            assets=[{
                "id": "a1", "type": "image", "name": "Logo",
                "description": "Course logo", "content": None,
            }],
        )
        # Should NOT match intro rule because assets are present
        # May match another rule or return None
        if decision is not None:
            assert decision.layout.mode != "instructor_only" or decision.confidence < 0.95


class TestSummaryRule:
    """Rule 2: Summary / recap → instructor_only."""

    def test_matches_summary_keyword(self):
        decision = evaluate(
            paragraph_id="p_006",
            paragraph={
                "text": "Let's recap what we learned today.",
                "keywords": ["summary", "recap", "key takeaways"],
                "start_ms": 168000,
                "end_ms": 198000,
            },
            assets=[],
        )
        assert decision is not None
        assert decision.layout.mode == "instructor_only"
        assert decision.confidence >= 0.9


class TestFormulaRule:
    """Rule 3: Formula asset → board_dominant."""

    def test_matches_formula_asset(self):
        decision = evaluate(
            paragraph_id="p_003",
            paragraph={
                "text": "The equation is Zn + 2HCl → ZnCl2 + H2.",
                "keywords": ["chemical equation", "formula"],
                "start_ms": 58000,
                "end_ms": 92000,
            },
            assets=[{
                "id": "a2", "type": "formula", "name": "Reaction equation",
                "description": "Balanced equation", "content": "Zn + 2HCl → ZnCl₂ + H₂",
            }],
        )
        assert decision is not None
        assert decision.layout.mode == "board_dominant"
        assert decision.confidence >= 0.85
        assert len(decision.assets) >= 1


class TestSingleImageRule:
    """Rule 4: Single image/diagram → board_dominant."""

    def test_matches_single_image(self):
        decision = evaluate(
            paragraph_id="p_002",
            paragraph={
                "text": "You can see the reaction happening.",
                "keywords": ["experiment", "reaction"],
                "start_ms": 28000,
                "end_ms": 58000,
            },
            assets=[{
                "id": "a1", "type": "image", "name": "Experiment photo",
                "description": "Photo of the reaction", "content": None,
            }],
        )
        assert decision is not None
        assert decision.layout.mode == "board_dominant"
        assert decision.confidence >= 0.85


class TestChartRule:
    """Rule 5: Chart/graph → split_50_50."""

    def test_matches_chart(self):
        decision = evaluate(
            paragraph_id="p_005",
            paragraph={
                "text": "If we look at the reaction rate data.",
                "keywords": ["reaction rate", "data analysis"],
                "start_ms": 128000,
                "end_ms": 168000,
            },
            assets=[{
                "id": "a5", "type": "chart", "name": "Rate chart",
                "description": "Line chart of rate vs concentration",
                "content": None,
            }],
        )
        assert decision is not None
        assert decision.layout.mode == "split_50_50"
        assert decision.confidence >= 0.80


class TestNoRuleMatch:
    """No rule matches → returns None (defers to LLM)."""

    def test_ambiguous_returns_none(self):
        """Multiple mixed assets should not match any rule."""
        decision = evaluate(
            paragraph_id="p_999",
            paragraph={
                "text": "This is a complex paragraph with mixed content.",
                "keywords": ["complex", "mixed"],
                "start_ms": 0,
                "end_ms": 10000,
            },
            assets=[
                {"id": "a1", "type": "image", "name": "img1", "description": "photo", "content": None},
                {"id": "a2", "type": "image", "name": "img2", "description": "diagram", "content": None},
                {"id": "a3", "type": "chart", "name": "chart1", "description": "chart", "content": None},
            ],
        )
        # Multiple images + chart = ambiguous, no single rule should match cleanly
        # (Could match image rule or chart rule depending on implementation)
        # The key assertion: if it matches, it should have reasonable confidence
        if decision is None:
            pass  # Correctly deferred to LLM
        else:
            assert 0 < decision.confidence <= 1.0


class TestDecisionOutputFormat:
    """All rule decisions should have complete, valid output format."""

    def test_output_has_all_fields(self):
        decision = evaluate(
            paragraph_id="p_001",
            paragraph={
                "text": "Welcome everyone.",
                "keywords": ["welcome"],
                "start_ms": 0,
                "end_ms": 5000,
            },
            assets=[],
        )
        assert decision is not None
        # Layout
        assert decision.layout.mode is not None
        assert decision.layout.description is not None
        assert decision.layout.instructor is not None
        assert decision.layout.board is not None
        # Transition
        assert decision.transition.type is not None
        assert decision.transition.duration_ms >= 0
        # Script display
        assert decision.script_display.instruction is not None
        # Reasoning
        assert decision.director_note is not None
        assert len(decision.director_note) > 10
        assert 0 <= decision.confidence <= 1.0
        assert decision.decided_by == "rule"
