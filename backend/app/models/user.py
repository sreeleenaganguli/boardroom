"""User model."""

from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="users", lazy="selectin")
    user_roles = relationship(
        "UserRole",
        back_populates="user",
        foreign_keys="UserRole.user_id",
        lazy="selectin",
    )
    datasets_uploaded = relationship(
        "Dataset", back_populates="uploader", foreign_keys="Dataset.uploaded_by", lazy="selectin"
    )
    dataset_accesses = relationship("DatasetAccess", back_populates="user", foreign_keys="DatasetAccess.user_id", lazy="selectin")
    analytics_runs = relationship("AnalyticsRun", back_populates="user", lazy="selectin")
    reports_created = relationship("Report", back_populates="creator", lazy="selectin")
    quality_reports = relationship("QualityReport", back_populates="generator", lazy="selectin")
    usage_records = relationship("UsageLedger", back_populates="user", lazy="selectin")
    audit_logs = relationship("AuditLog", back_populates="user", lazy="selectin")
