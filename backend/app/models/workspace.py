"""Workspace model."""

from sqlalchemy import String, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="workspaces", lazy="selectin")
    datasets = relationship("Dataset", back_populates="workspace", lazy="selectin")
    analytics_runs = relationship("AnalyticsRun", back_populates="workspace", lazy="selectin")
    reports = relationship("Report", back_populates="workspace", lazy="selectin")
    model_configs = relationship("ModelConfig", back_populates="workspace", lazy="selectin")
    usage_records = relationship("UsageLedger", back_populates="workspace", lazy="selectin")
    budgets = relationship("Budget", back_populates="workspace", lazy="selectin")
