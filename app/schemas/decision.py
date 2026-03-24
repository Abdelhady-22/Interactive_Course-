"""Pydantic schemas for Decision (agent output) — matches output.json contract."""
import uuid

from pydantic import BaseModel, Field

from app.models.decision import DecisionSource


# --- Sub-schemas that compose the decision ---

class InstructorLayout(BaseModel):
    """How the instructor video appears on screen."""
    visible: bool = True
    position: str = Field(..., description="e.g. bottom_right, left, center, full")
    size: str = Field(..., description="e.g. small, medium, large, full")
    style: str = Field("normal", description="e.g. pip, normal, semi_transparent")


class BoardLayout(BaseModel):
    """How the board/content area appears on screen."""
    visible: bool = True
    position: str = Field(..., description="e.g. left, right, center, full")
    size: str = Field(..., description="e.g. small, medium, large, full")


class LayoutDecision(BaseModel):
    """Full layout specification for a paragraph."""
    mode: str = Field(
        ...,
        description="One of: instructor_only, board_only, board_dominant, "
                    "instructor_dominant, split_50_50, instructor_behind_board, "
                    "instructor_pip, board_with_side_strip"
    )
    description: str = Field(
        ...,
        description="Human-readable description of the layout, e.g. "
                    "'Board takes the left 70% of the screen. Instructor as PiP bottom right.'"
    )
    instructor: InstructorLayout
    board: BoardLayout


class AssetDecision(BaseModel):
    """How a specific asset should be displayed."""
    id: str = Field(..., description="Asset UUID as string")
    type: str
    name: str
    position: str = Field(..., description="e.g. board_center, board_bottom, board_top, overlay")
    size: str = Field(..., description="e.g. small, medium, large")
    display_instruction: str = Field(
        ...,
        description="Human-readable instruction for how to show this asset"
    )
    appear_at_ms: int = Field(..., ge=0)
    disappear_at_ms: int = Field(..., ge=0)


class TransitionDecision(BaseModel):
    """How to transition into this paragraph's layout."""
    type: str = Field("fade", description="e.g. fade, slide_left, slide_right, cut, dissolve")
    duration_ms: int = Field(400, ge=0, le=2000)
    instruction: str = Field(
        ...,
        description="Human-readable transition instruction"
    )


class ScriptDisplayDecision(BaseModel):
    """How the script text appears on screen."""
    instruction: str = Field(
        ...,
        description="How to display the paragraph text"
    )
    keywords_to_highlight: list[str] = Field(default_factory=list)


# --- The full decision schema ---

class DecisionOutput(BaseModel):
    """The complete agent output for a single paragraph.
    This is the contract between agent and frontend.
    """
    paragraph_id: str
    layout: LayoutDecision
    assets: list[AssetDecision] = Field(default_factory=list)
    transition: TransitionDecision
    script_display: ScriptDisplayDecision
    director_note: str = Field(
        ...,
        description="Human-readable reasoning explaining why this layout was chosen"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    decided_by: DecisionSource


class DecisionResponse(BaseModel):
    """API response for a stored decision."""
    id: uuid.UUID
    paragraph_id: uuid.UUID
    layout: dict
    assets: list[dict]
    transition: dict
    script_display: dict
    director_note: str
    confidence: float
    decided_by: DecisionSource
    is_approved: bool

    model_config = {"from_attributes": True}


class DecisionOverride(BaseModel):
    """Request body for manually overriding a decision."""
    layout: LayoutDecision | None = None
    assets: list[AssetDecision] | None = None
    transition: TransitionDecision | None = None
    script_display: ScriptDisplayDecision | None = None
    director_note: str | None = None


class DecisionListResponse(BaseModel):
    """Response body for listing all decisions for a course."""
    course_id: uuid.UUID
    decisions: list[DecisionResponse]
    total: int
    approved_count: int


class PlaybackData(BaseModel):
    """The final playback JSON consumed by the learner player."""
    course_id: uuid.UUID
    title: str
    video_filename: str | None
    decisions: list[DecisionResponse]
