from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ActionResult:
    advance: bool = False
    next_step_key: str | None = None


from app.funnels.actions.add_tag import handle_add_tag
from app.funnels.actions.goto_step import handle_goto_step
from app.funnels.actions.open_track import handle_open_track
from app.funnels.actions.pay_product import handle_pay_product
from app.funnels.actions.signal import handle_signal
from app.funnels.actions.url import handle_url
