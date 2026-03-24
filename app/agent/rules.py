"""Rule-based decision engine — handles obvious cases before calling the LLM.

Rules are checked in priority order. First match wins.
Returns None if no rule applies (signals the engine to call the LLM).

Now context-aware: receives previous decisions and continuity hints
to make pinning decisions across paragraph sequences.
"""
from app.schemas.decision import (
    AssetDecision,
    BoardLayout,
    DecisionOutput,
    InstructorLayout,
    LayoutDecision,
    PositionContinuity,
    ScriptDisplayDecision,
    TransitionDecision,
)
from app.models.decision import DecisionSource


# Keywords that signal each rule
INTRO_KEYWORDS = {"welcome", "introduction", "hello", "greeting", "greetings", "course overview"}
SUMMARY_KEYWORDS = {"summary", "recap", "conclusion", "review", "key takeaways", "takeaways"}
FORMULA_ASSET_TYPES = {"formula"}
SINGLE_IMAGE_TYPES = {"image", "diagram", "infographic"}
DATA_VISUAL_TYPES = {"chart", "graph"}


def _normalize_keywords(keywords: list[str]) -> set[str]:
    """Lowercase all keywords for matching."""
    return {kw.lower().strip() for kw in keywords}


def _find_relevant_assets(paragraph: dict, assets: list[dict]) -> list[dict]:
    """Filter course assets to find ones relevant to this paragraph."""
    if not assets:
        return []

    kw_set = _normalize_keywords(paragraph.get("keywords", []))
    text_lower = paragraph.get("text", "").lower()
    relevant = []

    for asset in assets:
        asset_name_lower = asset.get("name", "").lower()
        asset_desc_lower = asset.get("description", "").lower()
        asset_type = asset.get("type", "").lower()

        keyword_match = any(
            kw in asset_name_lower or kw in asset_desc_lower
            for kw in kw_set
        )
        type_match = asset_type in kw_set
        name_in_text = asset_name_lower and any(
            word in text_lower for word in asset_name_lower.split()
            if len(word) > 3
        )

        if keyword_match or type_match or name_in_text:
            relevant.append(asset)

    return relevant


def _get_continuity_from_context(
    continuity_hint: dict | None,
    previous_decisions: list[dict] | None,
) -> PositionContinuity:
    """Build continuity info from context."""
    if not continuity_hint or not continuity_hint.get("pin_instructor"):
        return PositionContinuity(
            pin_instructor=False,
            transition_instructor=True,
            sequence_note="Standalone paragraph — no pinning.",
        )

    # Find the pin origin
    pin_from = None
    if previous_decisions:
        for prev in previous_decisions:
            cont = prev.get("continuity", {})
            if cont.get("pin_instructor"):
                pin_from = cont.get("pin_from_paragraph") or prev.get("paragraph_id")
                break

    return PositionContinuity(
        pin_instructor=True,
        pin_from_paragraph=pin_from,
        transition_instructor=continuity_hint.get("is_sequence_start", True),
        sequence_note=continuity_hint.get("note", "Part of a pinned asset sequence."),
    )


def _get_instructor_from_hint(continuity_hint: dict | None, default: dict) -> dict:
    """Get instructor position — use pinned position if available, else default."""
    if continuity_hint and continuity_hint.get("pin_instructor"):
        return {
            "visible": True,
            "position": continuity_hint.get("pin_position", default.get("position", "bottom_right")),
            "size": continuity_hint.get("pin_size", default.get("size", "small")),
            "style": continuity_hint.get("pin_style", default.get("style", "pip")),
        }
    return default


def _build_decision(
    paragraph_id: str,
    paragraph: dict,
    layout_mode: str,
    layout_desc: str,
    instructor: dict,
    board: dict,
    assets_to_show: list[dict],
    director_note: str,
    confidence: float,
    continuity: PositionContinuity | None = None,
    transition_type: str = "fade",
    transition_instruction: str = "Smooth fade transition into this segment.",
) -> DecisionOutput:
    """Helper to build a consistent DecisionOutput from rule parameters."""
    asset_decisions = []
    for a in assets_to_show:
        asset_decisions.append(
            AssetDecision(
                id=a["id"],
                type=a["type"],
                name=a["name"],
                position=a.get("position", "board_center"),
                size=a.get("size", "large"),
                display_instruction=a.get(
                    "display_instruction",
                    f"Show {a['name']} on the board as the primary visual."
                ),
                appear_at_ms=paragraph["start_ms"],
                disappear_at_ms=paragraph["end_ms"],
            )
        )

    return DecisionOutput(
        paragraph_id=paragraph_id,
        layout=LayoutDecision(
            mode=layout_mode,
            description=layout_desc,
            instructor=InstructorLayout(**instructor),
            board=BoardLayout(**board),
        ),
        assets=asset_decisions,
        transition=TransitionDecision(
            type=transition_type,
            duration_ms=400 if transition_type != "none" else 0,
            instruction=transition_instruction,
        ),
        script_display=ScriptDisplayDecision(
            instruction="Show the paragraph text at the bottom of the screen. Highlight keywords as the instructor speaks.",
            keywords_to_highlight=paragraph.get("keywords", []),
        ),
        continuity=continuity or PositionContinuity(),
        director_note=director_note,
        confidence=confidence,
        decided_by=DecisionSource.RULE,
    )


def evaluate(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    previous_decisions: list[dict] | None = None,
    continuity_hint: dict | None = None,
) -> DecisionOutput | None:
    """Attempt to decide layout using rules. Returns None if no rule matches.

    Args:
        paragraph_id: UUID string of the paragraph
        paragraph: Dict with keys: text, keywords, start_ms, end_ms
        assets: List of ALL available asset dicts for the course
        previous_decisions: Up to 3 previous decisions as context
        continuity_hint: Hint from sequence analyzer about pinning
    """
    kw_set = _normalize_keywords(paragraph.get("keywords", []))
    relevant_assets = _find_relevant_assets(paragraph, assets)
    is_pinned = continuity_hint and continuity_hint.get("pin_instructor", False)
    is_mid_sequence = continuity_hint and continuity_hint.get("is_sequence_middle", False)

    # Build continuity from context
    continuity = _get_continuity_from_context(continuity_hint, previous_decisions)

    # -------------------------------------------------------------------
    # Rule 1: Introduction / greeting — instructor only
    # -------------------------------------------------------------------
    if kw_set & INTRO_KEYWORDS and not relevant_assets:
        return _build_decision(
            paragraph_id=paragraph_id, paragraph=paragraph,
            layout_mode="instructor_only",
            layout_desc="Instructor fills the entire screen. No board or assets — welcome/introduction moment.",
            instructor={"visible": True, "position": "center", "size": "full", "style": "normal"},
            board={"visible": False, "position": "none", "size": "none"},
            assets_to_show=[],
            director_note="Introduction/greeting paragraph. Instructor is the sole focus — build personal connection.",
            confidence=0.95,
            continuity=PositionContinuity(pin_instructor=False, transition_instructor=True,
                                          sequence_note="Intro — instructor takes full screen."),
        )

    # -------------------------------------------------------------------
    # Rule 2: Summary / recap — instructor only
    # -------------------------------------------------------------------
    if kw_set & SUMMARY_KEYWORDS and not relevant_assets:
        return _build_decision(
            paragraph_id=paragraph_id, paragraph=paragraph,
            layout_mode="instructor_only",
            layout_desc="Instructor fills the entire screen for the summary/recap moment.",
            instructor={"visible": True, "position": "center", "size": "full", "style": "normal"},
            board={"visible": False, "position": "none", "size": "none"},
            assets_to_show=[],
            director_note="Summary/recap paragraph. Instructor wraps up — no visual distractions.",
            confidence=0.95,
            continuity=PositionContinuity(pin_instructor=False, transition_instructor=True,
                                          sequence_note="Summary — instructor takes full screen."),
        )

    # -------------------------------------------------------------------
    # Rule 3: Multiple assets → multi_asset_grid
    # -------------------------------------------------------------------
    if len(relevant_assets) >= 2 and not any(a["type"].lower() in DATA_VISUAL_TYPES for a in relevant_assets):
        default_instructor = {"visible": True, "position": "bottom_right", "size": "small", "style": "pip"}
        instructor = _get_instructor_from_hint(continuity_hint, default_instructor)
        grid_positions = ["grid_top_left", "grid_top_right", "grid_bottom_left", "grid_bottom_right"]

        return _build_decision(
            paragraph_id=paragraph_id, paragraph=paragraph,
            layout_mode="multi_asset_grid",
            layout_desc=f"Grid layout showing {len(relevant_assets)} assets. Instructor as PiP.",
            instructor=instructor,
            board={"visible": True, "position": "center", "size": "large"},
            assets_to_show=[
                {**a, "position": grid_positions[idx % 4], "size": "medium",
                 "display_instruction": f"Show '{a['name']}' in grid position {grid_positions[idx % 4]}."}
                for idx, a in enumerate(relevant_assets[:4])
            ],
            director_note=f"Multiple assets ({len(relevant_assets)}) relevant to this paragraph. Grid layout lets the learner see them all.",
            confidence=0.87,
            continuity=continuity,
            transition_type="none" if is_mid_sequence else "fade",
            transition_instruction="No instructor transition — pinned." if is_mid_sequence else "Fade into grid layout.",
        )

    # -------------------------------------------------------------------
    # Rule 4: Formula-heavy → board dominant
    # -------------------------------------------------------------------
    formula_assets = [a for a in relevant_assets if a["type"].lower() in FORMULA_ASSET_TYPES]
    if formula_assets:
        default_instructor = {"visible": True, "position": "bottom_right", "size": "small", "style": "pip"}
        instructor = _get_instructor_from_hint(continuity_hint, default_instructor)

        return _build_decision(
            paragraph_id=paragraph_id, paragraph=paragraph,
            layout_mode="board_dominant",
            layout_desc="Board takes the left 70% with formula. Instructor as PiP bottom right.",
            instructor=instructor,
            board={"visible": True, "position": "left", "size": "large"},
            assets_to_show=[
                {**a, "position": "board_center", "size": "large",
                 "display_instruction": f"Show formula '{a['name']}' large and centered on the board."}
                for a in formula_assets[:2]
            ],
            director_note="Formula-heavy paragraph. Formula is the core content — give it maximum screen space.",
            confidence=0.90,
            continuity=continuity,
            transition_type="none" if is_mid_sequence else "fade",
            transition_instruction="No instructor transition — pinned." if is_mid_sequence else "Smooth fade transition.",
        )

    # -------------------------------------------------------------------
    # Rule 5: Single image/diagram → board dominant or fullscreen_asset
    # -------------------------------------------------------------------
    image_assets = [a for a in relevant_assets if a["type"].lower() in SINGLE_IMAGE_TYPES]
    if len(image_assets) == 1:
        a = image_assets[0]
        # High-detail images → fullscreen_asset (no instructor)
        is_detailed = any(kw in {"detailed", "close-up", "experiment", "microscope", "photo"}
                         for kw in kw_set)

        if is_detailed and not is_pinned:
            return _build_decision(
                paragraph_id=paragraph_id, paragraph=paragraph,
                layout_mode="fullscreen_asset",
                layout_desc=f"'{a['name']}' fills the entire screen. No instructor visible.",
                instructor={"visible": False, "position": "none", "size": "none", "style": "normal"},
                board={"visible": True, "position": "full", "size": "full"},
                assets_to_show=[
                    {**a, "position": "board_center", "size": "large",
                     "display_instruction": f"Show '{a['name']}' at full resolution filling the entire screen."}
                ],
                director_note=f"High-detail visual '{a['name']}' — needs every pixel. Instructor steps away completely.",
                confidence=0.88,
                continuity=PositionContinuity(pin_instructor=False, transition_instructor=True,
                                              sequence_note="Fullscreen asset — instructor hidden."),
            )

        # Normal image → board_dominant
        default_instructor = {"visible": True, "position": "bottom_right", "size": "small", "style": "pip"}
        instructor = _get_instructor_from_hint(continuity_hint, default_instructor)

        return _build_decision(
            paragraph_id=paragraph_id, paragraph=paragraph,
            layout_mode="board_dominant",
            layout_desc="Board 70% with image/diagram. Instructor PiP bottom right.",
            instructor=instructor,
            board={"visible": True, "position": "left", "size": "large"},
            assets_to_show=[
                {**a, "position": "board_center", "size": "large",
                 "display_instruction": f"Show '{a['name']}' prominently on the board. {a.get('description', '')}"}
            ],
            director_note=f"Visual asset '{a['name']}' matches the context. Board dominant with instructor as PiP.",
            confidence=0.88,
            continuity=continuity,
            transition_type="none" if is_mid_sequence else "fade",
            transition_instruction="No instructor transition — pinned." if is_mid_sequence else "Smooth fade transition.",
        )

    # -------------------------------------------------------------------
    # Rule 6: Chart/graph → split_50_50 or split_60_40
    # -------------------------------------------------------------------
    data_assets = [a for a in relevant_assets if a["type"].lower() in DATA_VISUAL_TYPES]
    if data_assets:
        # Multiple data assets → split_60_40 (more room for data)
        if len(data_assets) >= 2:
            mode = "split_60_40"
            desc = "Board takes 60% with data visuals. Instructor 40%."
            instructor_size = "medium"
        else:
            mode = "split_50_50"
            desc = "Split screen: chart/graph left, instructor right."
            instructor_size = "medium"

        default_instructor = {"visible": True, "position": "right", "size": instructor_size, "style": "normal"}
        instructor = _get_instructor_from_hint(continuity_hint, default_instructor)

        return _build_decision(
            paragraph_id=paragraph_id, paragraph=paragraph,
            layout_mode=mode,
            layout_desc=desc,
            instructor=instructor,
            board={"visible": True, "position": "left", "size": "medium" if mode == "split_50_50" else "large"},
            assets_to_show=[
                {**a, "position": "board_center", "size": "large",
                 "display_instruction": f"Show '{a['name']}' on the left side. {a.get('description', '')}"}
                for a in data_assets[:2]
            ],
            director_note=f"Data visualization paragraph. {mode} gives equal weight to chart and explanation.",
            confidence=0.85,
            continuity=continuity,
            transition_type="none" if is_mid_sequence else "fade",
            transition_instruction="No instructor transition — pinned." if is_mid_sequence else "Smooth fade transition.",
        )

    # -------------------------------------------------------------------
    # No rule matched → pass to LLM
    # -------------------------------------------------------------------
    return None
