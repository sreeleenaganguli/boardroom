"""SemanticModel and ColumnProfile models."""

from sqlalchemy import String, Boolean, Integer, Float, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class SemanticModel(TimestampMixin, Base):
    __tablename__ = "semantic_models"

    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    semantic_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unique_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    null_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    dataset = relationship("Dataset", back_populates="semantic_models", lazy="selectin")
    column_profile = relationship(
        "ColumnProfile", back_populates="semantic_model", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )


class ColumnProfile(TimestampMixin, Base):
    __tablename__ = "column_profiles"

    semantic_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    min_val: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_val: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mean_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_dev: Mapped[float | None] = mapped_column(Float, nullable=True)
    histogram: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    top_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    semantic_model = relationship("SemanticModel", back_populates="column_profile", lazy="selectin")


class SchemaApproval(TimestampMixin, Base):
    """Versioned, user-approved business contract for an uploaded dataset."""
    __tablename__ = "schema_approvals"

    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="approved")
    contract: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    approved_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
