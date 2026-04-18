from __future__ import annotations

import enum
from datetime import datetime

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class FunnelStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    paused = "paused"


class StepMessageType(str, enum.Enum):
    text = "text"
    photo = "photo"
    document = "document"
    video_note = "video_note"
    voice = "voice"
    video = "video"


class ButtonType(str, enum.Enum):
    url = "url"
    callback = "callback"
    payment = "payment"


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


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_deeplink: Mapped[str | None] = mapped_column(String(255), index=True)

    tags: Mapped[list[UserTag]] = relationship(back_populates="user", cascade="all, delete-orphan")
    funnel_state: Mapped[UserFunnelState | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    purchases: Mapped[list[Purchase]] = relationship(back_populates="user", cascade="all, delete-orphan")
    scheduled_tasks: Mapped[list[ScheduledTask]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserTag(TimestampMixin, Base):
    __tablename__ = "user_tags"
    __table_args__ = (UniqueConstraint("user_id", "tag", name="uq_user_tags_user_id_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="tags")


class Funnel(TimestampMixin, Base):
    __tablename__ = "funnels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    steps: Mapped[list[FunnelStep]] = relationship(back_populates="funnel", cascade="all, delete-orphan")


class FunnelStep(TimestampMixin, Base):
    __tablename__ = "funnel_steps"
    __table_args__ = (UniqueConstraint("funnel_id", "step_order", name="uq_funnel_step_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    funnel_id: Mapped[int] = mapped_column(ForeignKey("funnels.id", ondelete="CASCADE"), index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(120), index=True)
    internal_name: Mapped[str | None] = mapped_column(String(255))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    delay_unit: Mapped[str] = mapped_column(String(20), nullable=False, default="seconds")
    delay_before_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trigger_conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    funnel: Mapped[Funnel] = relationship(back_populates="steps")
    messages: Mapped[list[StepMessage]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )
    buttons: Mapped[list[StepButton]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )


class StepMessage(TimestampMixin, Base):
    __tablename__ = "step_messages"
    __table_args__ = (UniqueConstraint("step_id", "message_order", name="uq_step_message_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("funnel_steps.id", ondelete="CASCADE"), index=True)
    message_order: Mapped[int] = mapped_column(Integer, nullable=False)
    message_type: Mapped[StepMessageType] = mapped_column(Enum(StepMessageType), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_file: Mapped[str | None] = mapped_column(String(1024))
    caption: Mapped[str | None] = mapped_column(Text)
    target_buttons_anchor: Mapped[str | None] = mapped_column(String(64))
    parse_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="HTML")
    delay_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    step: Mapped[FunnelStep] = relationship(back_populates="messages")


class StepButton(TimestampMixin, Base):
    __tablename__ = "step_buttons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("funnel_steps.id", ondelete="CASCADE"), index=True)
    button_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(String(255), nullable=False)
    button_type: Mapped[ButtonType] = mapped_column(Enum(ButtonType), nullable=False)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    step: Mapped[FunnelStep] = relationship(back_populates="buttons")


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    photo_file_id: Mapped[str | None] = mapped_column(String(1024))
    payment_url: Mapped[str | None] = mapped_column(String(2048))
    access_type: Mapped[str] = mapped_column(String(40), nullable=False, default="text")
    access_payload: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    purchases: Mapped[list[Purchase]] = relationship(back_populates="product", cascade="all, delete-orphan")


class Purchase(TimestampMixin, Base):
    __tablename__ = "purchases"
    __table_args__ = (Index("ix_purchases_ext_payment_id", "external_payment_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), nullable=False, default=PaymentStatus.pending
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_payment_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped[User] = relationship(back_populates="purchases")
    product: Mapped[Product] = relationship(back_populates="purchases")


class UserFunnelState(TimestampMixin, Base):
    __tablename__ = "user_funnel_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    funnel_id: Mapped[int] = mapped_column(ForeignKey("funnels.id", ondelete="CASCADE"), index=True)
    current_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("funnel_steps.id", ondelete="SET NULL"), index=True
    )
    last_step_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[FunnelStatus] = mapped_column(
        Enum(FunnelStatus), nullable=False, default=FunnelStatus.active
    )

    user: Mapped[User] = relationship(back_populates="funnel_state")


class CommunityTrack(TimestampMixin, Base):
    __tablename__ = "community_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    messages_payload: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserActionLog(TimestampMixin, Base):
    __tablename__ = "user_action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    funnel_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("funnel_steps.id", ondelete="SET NULL"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ButtonClickStat(TimestampMixin, Base):
    __tablename__ = "button_click_stats"
    __table_args__ = (Index("ix_button_click_stats_step_button", "step_button_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_button_id: Mapped[int] = mapped_column(
        ForeignKey("step_buttons.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class Broadcast(TimestampMixin, Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    segment_logic: Mapped[str] = mapped_column(String(10), nullable=False, default="OR")
    segment_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False, default="text")
    content_text: Mapped[str | None] = mapped_column(Text)
    content_file: Mapped[str | None] = mapped_column(String(1024))
    buttons_payload: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")


class BroadcastRecipient(TimestampMixin, Base):
    __tablename__ = "broadcast_recipients"
    __table_args__ = (UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipient"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delivery_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")


class ScheduledTask(TimestampMixin, Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (Index("ix_scheduled_tasks_run_at_status", "run_at", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ScheduledTaskStatus] = mapped_column(
        Enum(ScheduledTaskStatus), nullable=False, default=ScheduledTaskStatus.pending
    )

    user: Mapped[User] = relationship(back_populates="scheduled_tasks")


class BotSetting(TimestampMixin, Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[dict | None] = mapped_column(JSONB)


class SupportMessageLink(TimestampMixin, Base):
    __tablename__ = "support_message_links"
    __table_args__ = (
        UniqueConstraint("support_chat_id", "support_message_id", name="uq_support_chat_message"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    support_chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    support_message_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
