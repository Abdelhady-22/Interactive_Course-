"""Asset model — visual resources (images, diagrams, charts, formulas, etc.)."""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AssetType(str, enum.Enum):
    """Types of visual assets."""
    IMAGE = "image"
    DIAGRAM = "diagram"
    CHART = "chart"
    FORMULA = "formula"
    INFOGRAPHIC = "infographic"
    GRAPH = "graph"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[AssetType] = mapped_column(Enum(AssetType), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    course = relationship("Course", back_populates="assets")

    def __repr__(self) -> str:
        return f"<Asset(id={self.id}, type={self.type}, name='{self.name}')>"
