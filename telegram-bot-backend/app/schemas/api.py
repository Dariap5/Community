from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.step_config import StepConfig


class FunnelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    entry_key: str | None = Field(default=None, max_length=120, pattern=r"^[a-z0-9_]+$")
    cross_entry_behavior: Literal["allow", "deny"] = "allow"
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")


class FunnelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    entry_key: str | None = Field(default=None, max_length=120, pattern=r"^[a-z0-9_]+$")
    is_active: bool | None = None
    is_archived: bool | None = None
    cross_entry_behavior: Literal["allow", "deny"] | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")


class FunnelStepSummary(BaseModel):
    id: UUID
    order: int
    name: str
    step_key: str
    is_active: bool
    messages_count: int
    buttons_count: int
    delay_before_hours: float

    model_config = ConfigDict(from_attributes=True)


class FunnelRead(BaseModel):
    id: UUID
    name: str
    entry_key: str | None
    is_active: bool
    is_archived: bool
    cross_entry_behavior: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    steps_count: int
    active_users_count: int
    steps: list[FunnelStepSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class FunnelListItem(BaseModel):
    id: UUID
    name: str
    entry_key: str | None
    is_active: bool
    is_archived: bool
    steps_count: int
    active_users_count: int

    model_config = ConfigDict(from_attributes=True)


class StepCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    step_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    order: int | None = Field(default=None, ge=1)
    is_active: bool = True
    config: StepConfig = Field(default_factory=StepConfig)

    model_config = ConfigDict(extra="forbid")


class StepUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    step_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    is_active: bool
    config: StepConfig

    model_config = ConfigDict(extra="forbid")


class StepReorder(BaseModel):
    step_ids_in_order: list[UUID]

    model_config = ConfigDict(extra="forbid")


class StepRead(BaseModel):
    id: UUID
    funnel_id: UUID
    order: int
    name: str
    step_key: str
    is_active: bool
    config: StepConfig
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | list | str | int | float | bool | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail