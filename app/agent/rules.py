"""Rule-based decision engine — handles obvious cases before calling the LLM.

Rules are checked in priority order. First match wins.
Returns None if no rule applies (signals the engine to call the LLM).

IMPORTANT: The `assets` parameter receives ALL course assets. Rules must
filter for relevant assets by matching keywords/context, not just checking
if any assets exist.
"""
from app.schemas.decision import (
    AssetDecision,
    BoardLayout,
    DecisionOutput,
    InstructorLayout,
    LayoutDecision,
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
    """Filter course assets to find ones relevant to this paragraph.

    An asset is considered relevant if:
    1. Any of the paragraph's keywords appear in the asset name or description
    2. The asset type matches a keyword concept (e.g. "formula" keyword + formula asset)
    """
    if not assets:
        return []

    kw_set = _normalize_keywords(paragraph.get("keywords", []))
    text_lower = paragraph.get("text", "").lower()
    relevant = []

    for asset in assets:
        asset_name_lower = asset.get("name", "").lower()
        asset_desc_lower = asset.get("description", "").lower()
        asset_type = asset.get("type", "").lower()

        # Check if any keyword appears in asset name/description
        keyword_match = any(
            kw in asset_name_lower or kw in asset_desc_lower
            for kw in kw_set
        )

        # Check if asset type matches keyword concepts
        type_match = asset_type in kw_set

        # Check if asset name/content appears in the paragraph text
        name_in_text = asset_name_lower and any(
            word in text_lower for word in asset_name_lower.split()
            if len(word) > 3  # skip short words
        )

        if keyword_match or type_match or name_in_text:
            relevant.append(asset)

    return relevant


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
            type="fade",
            duration_ms=400,
            instruction="Smooth fade transition into this segment.",
        ),
        script_display=ScriptDisplayDecision(
            instruction="Show the paragraph text at the bottom of the screen. Highlight keywords as the instructor speaks.",
            keywords_to_highlight=paragraph.get("keywords", []),
        ),
        director_note=director_note,
        confidence=confidence,
        decided_by=DecisionSource.RULE,
    )


def evaluate(paragraph_id: str, paragraph: dict, assets: list[dict]) -> DecisionOutput | None:
    """Attempt to decide layout using rules. Returns None if no rule matches.

    Args:
        paragraph_id: UUID string of the paragraph
        paragraph: Dict with keys: text, keywords, start_ms, end_ms
        assets: List of ALL available asset dicts for the course
    """
    kw_set = _normalize_keywords(paragraph.get("keywords", []))

    # Find assets relevant to THIS paragraph (not all course assets)
    relevant_assets = _find_relevant_assets(paragraph, assets)
    relevant_types = {a["type"].lower() for a in relevant_assets}

    # -------------------------------------------------------------------
    # Rule 1: Introduction / greeting — instructor only, no relevant assets
    # -------------------------------------------------------------------
    if kw_set & INTRO_KEYWORDS and not relevant_assets:
        return _build_decision(
            paragraph_id=paragraph_id,
            paragraph=paragraph,
            layout_mode="instructor_only",
            layout_desc="Instructor fills the entire screen. No board or assets — this is a welcome/introduction moment.",
            instructor={"visible": True, "position": "center", "size": "full", "style": "normal"},
            board={"visible": False, "position": "none", "size": "none"},
            assets_to_show=[],
            director_note="This is an introduction/greeting paragraph. The instructor should be the sole focus — no distractions. Build personal connection with the learner.",
            confidence=0.95,
        )

    # -------------------------------------------------------------------
    # Rule 2: Summary / recap — instructor only, no relevant assets
    # -------------------------------------------------------------------
    if kw_set & SUMMARY_KEYWORDS and not relevant_assets:
        return _build_decision(
            paragraph_id=paragraph_id,
            paragraph=paragraph,
            layout_mode="instructor_only",
            layout_desc="Instructor fills the entire screen for the summary/recap moment.",
            instructor={"visible": True, "position": "center", "size": "full", "style": "normal"},
            board={"visible": False, "position": "none", "size": "none"},
            assets_to_show=[],
            director_note="This is a summary/recap paragraph. The instructor wraps up key points — keep focus on them. No visual distractions needed.",
            confidence=0.95,
        )

    # -------------------------------------------------------------------
    # Rule 3: Formula-heavy — board dominant with formula centered
    # -------------------------------------------------------------------
    formula_assets = [a for a in relevant_assets if a["type"].lower() in FORMULA_ASSET_TYPES]
    if formula_assets:
        return _build_decision(
            paragraph_id=paragraph_id,
            paragraph=paragraph,
            layout_mode="board_dominant",
            layout_desc="Board takes the left 70% of the screen with the formula prominently displayed. Instructor appears as PiP in the bottom right.",
            instructor={"visible": True, "position": "bottom_right", "size": "small", "style": "pip"},
            board={"visible": True, "position": "left", "size": "large"},
            assets_to_show=[
                {**a, "position": "board_center", "size": "large",
                 "display_instruction": f"Show the formula '{a['name']}' large and centered on the board. This is the core content of this moment."}
                for a in formula_assets[:2]  # max 2 formulas
            ],
            director_note=f"Formula-heavy paragraph. The formula is the core content — give it maximum screen space. Instructor steps back to PiP so the learner focuses on the equation.",
            confidence=0.90,
        )

    # -------------------------------------------------------------------
    # Rule 4: Single image/diagram/experiment — board dominant
    # -------------------------------------------------------------------
    image_assets = [a for a in relevant_assets if a["type"].lower() in SINGLE_IMAGE_TYPES]
    if len(image_assets) == 1:
        a = image_assets[0]
        return _build_decision(
            paragraph_id=paragraph_id,
            paragraph=paragraph,
            layout_mode="board_dominant",
            layout_desc="Board takes the left 70% of the screen showing the image/diagram. Instructor appears as PiP in the bottom right.",
            instructor={"visible": True, "position": "bottom_right", "size": "small", "style": "pip"},
            board={"visible": True, "position": "left", "size": "large"},
            assets_to_show=[
                {**a, "position": "board_center", "size": "large",
                 "display_instruction": f"Show '{a['name']}' prominently on the board. {a.get('description', '')}"}
            ],
            director_note=f"Single visual asset '{a['name']}' matches the paragraph context. Give it the screen — the instructor talks over it from PiP.",
            confidence=0.88,
        )

    # -------------------------------------------------------------------
    # Rule 5: Chart/graph data — split 50/50
    # -------------------------------------------------------------------
    data_assets = [a for a in relevant_assets if a["type"].lower() in DATA_VISUAL_TYPES]
    if data_assets and not formula_assets:
        return _build_decision(
            paragraph_id=paragraph_id,
            paragraph=paragraph,
            layout_mode="split_50_50",
            layout_desc="Split screen: instructor on the right, chart/graph on the left. Equal importance.",
            instructor={"visible": True, "position": "right", "size": "medium", "style": "normal"},
            board={"visible": True, "position": "left", "size": "medium"},
            assets_to_show=[
                {**a, "position": "board_center", "size": "large",
                 "display_instruction": f"Show '{a['name']}' on the left side. {a.get('description', '')}"}
                for a in data_assets[:1]
            ],
            director_note=f"Data visualization paragraph. The chart/graph needs equal screen time with the instructor who explains it. Split 50/50 is the right call.",
            confidence=0.85,
        )

    # -------------------------------------------------------------------
    # No rule matched — pass to LLM
    # -------------------------------------------------------------------
    return None
