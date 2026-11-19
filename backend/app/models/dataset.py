"""Dataset, DatasetAccess, and DatasetVersion models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, Integer, BigInteger, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, processing, ready, error

    # Relationships
    workspace = relationship("Workspace", back_populates="datasets", lazy="selectin")
    uploader = relationship("User", back_populates="datasets_uploaded", foreign_keys=[uploaded_by], lazy="selectin")
    accesses = relationship("DatasetAccess", back_populates="dataset", lazy="selectin", cascade="all, delete-orphan")
    versions = relationship("DatasetVersion", back_populates="dataset", lazy="selectin", cascade="all, delete-orphan")
    semantic_models = relationship("SemanticModel", back_populates="dataset", lazy="selectin", cascade="all, delete-orphan")
    quality_reports = relationship("QualityReport", back_populates="dataset", lazy="selectin", cascade="all, delete-orphan")
class DatasetAccess(Base):
    __tablename__ = "dataset_accesses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    access_level: Mapped[str] = mapped_column(
        String(50), default="read", nullable=False
    )  # read, write, admin
    granted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    dataset = relationship("Dataset", back_populates="accesses", lazy="selectin")
    user = relationship("User", back_populates="dataset_accesses", foreign_keys=[user_id], lazy="selectin")
    granter = relationship("User", foreign_keys=[granted_by], lazy="selectin")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    change_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    dataset = relationship("Dataset", back_populates="versions", lazy="selectin")
    creator = relationship("User", foreign_keys=[created_by], lazy="selectin")
