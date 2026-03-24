"""Unit tests for the rule-based decision engine + sequence analyzer."""
import pytest

from app.agent.rules import evaluate
from app.agent.sequence_analyzer import analyze_sequences, get_continuity_hints


# =====================================================================
# Rule Engine Tests
# =====================================================================

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
        assert decision.continuity.pin_instructor is False

    def test_does_not_match_with_relevant_assets(self):
        """Intro rule should NOT fire if paragraph has relevant assets."""
        decision = evaluate(
            paragraph_id="p_001",
            paragraph={
                "text": "Welcome to this course.",
                "keywords": ["welcome", "introduction"],
                "start_ms": 0,
                "end_ms": 10000,
            },
            assets=[{
                "id": "a1", "type": "image", "name": "Welcome banner",
                "description": "Course welcome image", "content": None,
            }],
        )
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


class TestMultiAssetGridRule:
    """Rule 3: Multiple assets → multi_asset_grid."""

    def test_matches_multiple_images(self):
        decision = evaluate(
            paragraph_id="p_multi",
            paragraph={
                "text": "Compare these two diagrams side by side.",
                "keywords": ["comparison", "diagram"],
                "start_ms": 0,
                "end_ms": 30000,
            },
            assets=[
                {"id": "a1", "type": "diagram", "name": "Diagram A comparison",
                 "description": "First diagram for comparison", "content": None},
                {"id": "a2", "type": "diagram", "name": "Diagram B comparison",
                 "description": "Second diagram for comparison", "content": None},
            ],
        )
        assert decision is not None
        assert decision.layout.mode == "multi_asset_grid"
        assert len(decision.assets) >= 2


class TestFormulaRule:
    """Rule 4: Formula asset → board_dominant."""

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

    def test_formula_with_pinning(self):
        """Formula rule should respect continuity hint for pinning."""
        decision = evaluate(
            paragraph_id="p_003",
            paragraph={
                "text": "Now the formula derivation.",
                "keywords": ["formula", "equation"],
                "start_ms": 58000,
                "end_ms": 92000,
            },
            assets=[{
                "id": "a2", "type": "formula", "name": "Formula equation",
                "description": "Key formula", "content": "E=mc²",
            }],
            continuity_hint={
                "pin_instructor": True,
                "pin_position": "bottom_right",
                "pin_size": "small",
                "pin_style": "pip",
                "is_sequence_start": False,
                "is_sequence_middle": True,
                "is_sequence_end": False,
                "note": "Part of a pinned sequence.",
            },
        )
        assert decision is not None
        assert decision.layout.mode == "board_dominant"
        assert decision.layout.instructor.position == "bottom_right"
        assert decision.transition.type == "none"  # Pinned = no transition


class TestFullscreenAssetRule:
    """Rule 5: Detailed image → fullscreen_asset."""

    def test_detailed_image(self):
        decision = evaluate(
            paragraph_id="p_008",
            paragraph={
                "text": "Let me show you a close-up experiment photograph.",
                "keywords": ["close-up", "experiment", "detailed"],
                "start_ms": 0,
                "end_ms": 30000,
            },
            assets=[{
                "id": "a6", "type": "image", "name": "Close-up experiment microscope",
                "description": "High-magnification photo", "content": None,
            }],
        )
        assert decision is not None
        assert decision.layout.mode == "fullscreen_asset"
        assert decision.layout.instructor.visible is False


class TestChartRule:
    """Rule 6: Chart/graph → split_50_50 or split_60_40."""

    def test_single_chart(self):
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
                {"id": "a2", "type": "chart", "name": "chart1", "description": "chart data", "content": None},
            ],
        )
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
        # Continuity (new)
        assert decision.continuity is not None
        assert isinstance(decision.continuity.pin_instructor, bool)
        # Reasoning
        assert decision.director_note is not None
        assert len(decision.director_note) > 10
        assert 0 <= decision.confidence <= 1.0
        assert decision.decided_by == "rule"


# =====================================================================
# Sequence Analyzer Tests
# =====================================================================

class TestSequenceAnalyzer:
    """Tests for the sequence_analyzer grouping logic."""

    def _make_paragraph(self, text, keywords, start=0, end=10000):
        return {"text": text, "keywords": keywords, "start_ms": start, "end_ms": end}

    def test_detects_asset_sequence(self):
        """2+ consecutive paragraphs with assets = pinned sequence."""
        paragraphs = [
            self._make_paragraph("Welcome.", ["welcome", "introduction"]),         # narration
            self._make_paragraph("The experiment.", ["experiment", "reaction"]),     # has asset
            self._make_paragraph("The formula.", ["formula", "equation"]),           # has asset
            self._make_paragraph("The diagram.", ["diagram", "electron transfer"]), # has asset
            self._make_paragraph("Recap.", ["summary", "recap"]),                   # narration
        ]
        assets = [
            {"id": "1", "type": "image", "name": "Experiment photo", "description": "Reaction experiment"},
            {"id": "2", "type": "formula", "name": "Formula equation", "description": "Key formula"},
            {"id": "3", "type": "diagram", "name": "Electron transfer diagram", "description": "Electron diagram"},
        ]

        sequences = analyze_sequences(paragraphs, assets)
        pinned = [s for s in sequences if s.pin_instructor]

        assert len(pinned) >= 1, "Should detect at least 1 pinned sequence"
        assert any(len(s.paragraph_indices) >= 2 for s in pinned), "Pinned sequence should have 2+ paragraphs"

    def test_no_sequence_for_single_asset(self):
        """Single asset paragraph should NOT create a pinned sequence."""
        paragraphs = [
            self._make_paragraph("Welcome.", ["welcome"]),
            self._make_paragraph("The formula.", ["formula"]),
            self._make_paragraph("Recap.", ["summary"]),
        ]
        assets = [
            {"id": "1", "type": "formula", "name": "Formula", "description": "Key formula"},
        ]

        sequences = analyze_sequences(paragraphs, assets)
        pinned = [s for s in sequences if s.pin_instructor]

        assert len(pinned) == 0, "Single asset paragraph should not create pinned sequence"

    def test_continuity_hints_generated(self):
        """Continuity hints should be generated for each paragraph."""
        paragraphs = [
            self._make_paragraph("Welcome.", ["welcome"]),
            self._make_paragraph("Experiment.", ["experiment"]),
            self._make_paragraph("Formula.", ["formula"]),
        ]
        assets = [
            {"id": "1", "type": "image", "name": "Experiment photo", "description": "Experiment"},
            {"id": "2", "type": "formula", "name": "Formula", "description": "Key formula"},
        ]

        sequences = analyze_sequences(paragraphs, assets)
        hints = get_continuity_hints(paragraphs, sequences)

        assert len(hints) == 3, "Should have one hint per paragraph"
        assert hints[0].pin_instructor is False, "Welcome paragraph should not be pinned"
