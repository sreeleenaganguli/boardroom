"""UsageLedger, Budget, and BudgetAlert models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analytics_runs.id", ondelete="SET NULL"), nullable=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="usage_records", lazy="selectin")
    model = relationship("AIModel", back_populates="usage_records", lazy="selectin")
    workspace = relationship("Workspace", back_populates="usage_records", lazy="selectin")
    run = relationship("AnalyticsRun", back_populates="usage_records", lazy="selectin")


class Budget(TimestampMixin, Base):
    __tablename__ = "budgets"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    monthly_limit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alert_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    current_spend: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    workspace = relationship("Workspace", back_populates="budgets", lazy="selectin")
    alerts = relationship("BudgetAlert", back_populates="budget", lazy="selectin", cascade="all, delete-orphan")


class BudgetAlert(Base):
    __tablename__ = "budget_alerts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    budget_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # warning, critical, over_budget
    message: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_pct: Mapped[float] = mapped_column(Float, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    budget = relationship("Budget", back_populates="alerts", lazy="selectin")
    acknowledger = relationship("User", foreign_keys=[acknowledged_by], lazy="selectin")
