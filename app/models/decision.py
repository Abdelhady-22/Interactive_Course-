"""Decision model — stores the agent's layout decision per paragraph."""
import enum
import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DecisionSource(str, enum.Enum):
    """How the decision was made."""
    RULE = "rule"
    LLM = "llm"
    HUMAN_OVERRIDE = "human_override"


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paragraph_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paragraphs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Layout decision — matches output.json schema
    layout: Mapped[dict] = mapped_column(JSON, nullable=False)
    assets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    transition: Mapped[dict] = mapped_column(JSON, nullable=False)
    script_display: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Agent reasoning
    director_note: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    decided_by: Mapped[DecisionSource] = mapped_column(
        Enum(DecisionSource), nullable=False
    )

    # Approval
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    paragraph = relationship("Paragraph", back_populates="decision")

    def __repr__(self) -> str:
        mode = self.layout.get("mode", "?") if self.layout else "?"
        return f"<Decision(id={self.id}, layout={mode}, decided_by={self.decided_by})>"
