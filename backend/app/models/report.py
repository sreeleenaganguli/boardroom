"""Report and ReportTemplate models."""

from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ReportTemplate(TimestampMixin, Base):
    __tablename__ = "report_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    layout_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    reports = relationship("Report", back_populates="template", lazy="selectin")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    layout: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="reports", lazy="selectin")
    creator = relationship("User", back_populates="reports_created", foreign_keys=[created_by], lazy="selectin")
    template = relationship("ReportTemplate", back_populates="reports", lazy="selectin")
