import uuid
from datetime import datetime
import enum
from typing import Optional, List

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class FunnelCrossEntryBehavior(str, enum.Enum):
    allow = "allow"
    deny = "deny"

class FunnelStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    completed = "completed"

class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"

class ScheduledTaskStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    canceled = "canceled"
    failed = "failed"

class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    source_deeplink: Mapped[str | None] = mapped_column(String(255), index=True)
    selected_track_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(default=func.now())

    tags: Mapped[list["UserTag"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    funnel_states: Mapped[list["UserFunnelState"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    purchases: Mapped[list["Purchase"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    scheduled_tasks: Mapped[list["ScheduledTask"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    selected_track: Mapped[Optional["Track"]] = relationship()

class UserTag(Base):
    __tablename__ = "user_tags"
    __table_args__ = (UniqueConstraint("user_id", "tag", name="uq_user_tags_user_id_tag"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True, index=True)
    tag: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)
    assigned_at: Mapped[datetime] = mapped_column(default=func.now())

    user: Mapped["User"] = relationship(back_populates="tags")

class Funnel(Base):
    __tablename__ = "funnels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    entry_key: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    is_archived: Mapped[bool] = mapped_column(default=False)
    cross_entry_behavior: Mapped[FunnelCrossEntryBehavior] = mapped_column(
        Enum(FunnelCrossEntryBehavior), default=FunnelCrossEntryBehavior.allow
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    steps: Mapped[list["FunnelStep"]] = relationship(back_populates="funnel", cascade="all, delete-orphan", order_by="FunnelStep.order")
    user_states: Mapped[list["UserFunnelState"]] = relationship(back_populates="funnel", cascade="all, delete-orphan")

class FunnelStep(Base):
    __tablename__ = "funnel_steps"
    __table_args__ = (
        UniqueConstraint("funnel_id", "step_key", name="uq_funnel_step_key"),
        Index("ix_funnel_steps_funnel_order", "funnel_id", "order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    funnel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funnels.id", ondelete="CASCADE"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    step_key: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    funnel: Mapped["Funnel"] = relationship(back_populates="steps")

class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

class UserFunnelState(Base):
    __tablename__ = "user_funnel_state"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    funnel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funnels.id", ondelete="CASCADE"), index=True)
    current_step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funnel_steps.id", ondelete="SET NULL"), index=True)
    status: Mapped[FunnelStatus] = mapped_column(Enum(FunnelStatus), default=FunnelStatus.active)
    started_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="funnel_states")
    funnel: Mapped["Funnel"] = relationship(back_populates="user_states")
    current_step: Mapped[Optional["FunnelStep"]] = relationship()

class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    photo_file_id: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="product", cascade="all, delete-orphan")

class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.pending)
    payment_provider_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column()

    user: Mapped["User"] = relationship(back_populates="purchases")
    product: Mapped["Product"] = relationship(back_populates="purchases")

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    execute_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ScheduledTaskStatus] = mapped_column(Enum(ScheduledTaskStatus), default=ScheduledTaskStatus.pending)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    user: Mapped["User"] = relationship(back_populates="scheduled_tasks")

class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_text: Mapped[str | None] = mapped_column(Text)
    is_encrypted: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
