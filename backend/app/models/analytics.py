"""AnalyticsRun and RunStep models."""

from sqlalchemy import String, Boolean, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class AnalyticsRun(TimestampMixin, Base):
    __tablename__ = "analytics_runs"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    natural_language_query: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, running, completed, failed, cancelled
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    workspace = relationship("Workspace", back_populates="analytics_runs", lazy="selectin")
    user = relationship("User", back_populates="analytics_runs", lazy="selectin")
    steps = relationship("RunStep", back_populates="run", lazy="selectin", cascade="all, delete-orphan")
    usage_records = relationship("UsageLedger", back_populates="run", lazy="selectin")


class RunStep(TimestampMixin, Base):
    __tablename__ = "run_steps"

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analytics_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    step_type: Mapped[str] = mapped_column(String(100), nullable=False)
    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    run = relationship("AnalyticsRun", back_populates="steps", lazy="selectin")
