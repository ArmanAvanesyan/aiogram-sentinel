"""Safe configurable callback rejection; never contains another user's state."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from aiogram import Bot
from aiogram.types import CallbackQuery

RejectionReason = Literal["stale", "unsupported", "busy"]


@dataclass(frozen=True)
class CallbackRejection:
    callback: CallbackQuery
    bot: Bot
    reason: RejectionReason


CallbackRejectionResponder = Callable[[CallbackRejection], Awaitable[None]]
