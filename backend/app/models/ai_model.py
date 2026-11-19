"""AIProvider, AIModel, and ModelConfig models."""

from sqlalchemy import String, Boolean, Integer, Float, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class AIProvider(TimestampMixin, Base):
    __tablename__ = "ai_providers"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    models = relationship("AIModel", back_populates="provider", lazy="selectin", cascade="all, delete-orphan")


class AIModel(TimestampMixin, Base):
    __tablename__ = "ai_models"

    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_providers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # chat, completion, embedding
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    input_price_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_price_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    provider = relationship("AIProvider", back_populates="models", lazy="selectin")
    configs = relationship("ModelConfig", back_populates="model", lazy="selectin", cascade="all, delete-orphan")
    usage_records = relationship("UsageLedger", back_populates="model", lazy="selectin")


class ModelConfig(TimestampMixin, Base):
    __tablename__ = "model_configs"

    model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)
    top_p: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    model = relationship("AIModel", back_populates="configs", lazy="selectin")
    workspace = relationship("Workspace", back_populates="model_configs", lazy="selectin")
