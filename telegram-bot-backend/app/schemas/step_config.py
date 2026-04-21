from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID, uuid4


class Delay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = Field(ge=0)
    unit: Literal["seconds", "minutes", "hours", "days"]


class TriggerCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["always", "has_tags", "not_has_tags"] = "always"
    tags: list[str] = Field(default_factory=list)


class VisibilityCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_tags: list[str] = Field(default_factory=list)
    not_has_tags: list[str] = Field(default_factory=list)


class ButtonActionUrl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["url"]
    value: str


class ButtonActionPayProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["pay_product"]
    value: str


class ButtonActionGotoStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["goto_step"]
    value: str


class ButtonActionAddTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["add_tag"]
    value: str


class ButtonActionOpenTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["open_track"]
    value: str


class ButtonActionSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["signal"]
    value: str

ButtonAction = Annotated[
    Union[
    ButtonActionUrl,
    ButtonActionPayProduct,
    ButtonActionGotoStep,
    ButtonActionAddTag,
    ButtonActionOpenTrack,
    ButtonActionSignal,
    ],
    Field(discriminator="type"),
]


class Button(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    text: str = Field(min_length=1, max_length=64)
    action: ButtonAction
    visible_if: VisibilityCondition = Field(default_factory=VisibilityCondition)


class MessageContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    type: Literal["text", "photo", "document", "video", "video_note", "voice"]
    content_text: Optional[str] = None
    file_id: Optional[str] = None
    parse_mode: Literal["HTML", "Markdown"] = "HTML"
    delay_after: int = Field(ge=0, default=0)


class ButtonGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    type: Literal["buttons"]
    buttons: list[Button] = Field(default_factory=list)

Block = Annotated[Union[MessageContent, ButtonGroup], Field(discriminator="type")]


class AfterStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    add_tags: list[str] = Field(default_factory=list)
    next_step: str = "auto"
    dozhim_if_no_click_hours: Optional[int] = None


class StepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delay_before: Delay = Field(default_factory=lambda: Delay(value=0, unit="seconds"))
    trigger_condition: TriggerCondition = Field(default_factory=TriggerCondition)
    wait_for_payment: bool = False
    linked_product_id: Optional[UUID] = None
    blocks: list[Block] = Field(default_factory=list)
    after_step: AfterStep = Field(default_factory=AfterStep)

    @field_validator("blocks")
    @classmethod
    def validate_blocks_order(cls, v):
        return v
