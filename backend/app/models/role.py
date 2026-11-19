"""Role model."""

from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    role_permissions = relationship("RolePermission", back_populates="role", lazy="selectin", cascade="all, delete-orphan")
    user_roles = relationship("UserRole", back_populates="role", lazy="selectin", cascade="all, delete-orphan")
