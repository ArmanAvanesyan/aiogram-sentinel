"""Track reply-keyboard provenance while idle controls overlay application UI."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import replace

from aiogram_nav.models import ConversationKey, NavigationIntent, VersionedSnapshot
from aiogram_nav.storage.memory import MemoryNavigationRepository

from ...errors import SchemaUnsupported
from ...models import RuntimeSnapshot
from .codec import COMPONENT


def active(record: RuntimeSnapshot | None) -> bool:
    if record is None:
        return False
    prompt = record.idle.prompt
    if prompt is not None and prompt.controls in {"reply", "hybrid"}:
        return True
    component = record.components.get(COMPONENT)
    if isinstance(component, Mapping):
        flag = component.get("reply_overlay", False)
        if type(flag) is not bool:
            raise SchemaUnsupported("Invalid reply-keyboard provenance marker")
        return flag
    return False


def operation_id(touch_id: str) -> str:
    return "idle-overlay:" + hashlib.sha256(touch_id.encode()).hexdigest()


async def prepare(memory: MemoryNavigationRepository, key: ConversationKey, touch_id: str) -> None:
    current = await memory.load(key)
    if current is None:
        return
    snapshot = current.snapshot
    await memory.prepare(
        key,
        expected_version=current.version,
        intent=NavigationIntent(
            operation_id(touch_id),
            snapshot.node_id,
            params=snapshot.params,
            history="none",
            source="idle-overlay",
            accepted_activity=False,
        ),
    )


def visible(
    current: VersionedSnapshot | None, record: RuntimeSnapshot | None
) -> VersionedSnapshot | None:
    if current is None or not active(record):
        return current
    # Keep the raw ledger and its receipts unchanged. Only presentation/input
    # provenance is invalid while Continue/Cancel owns the physical reply tray.
    return replace(
        current,
        snapshot=replace(
            current.snapshot,
            view=replace(
                current.snapshot.view, reply_keyboard_key=None, reply_keyboard_locale=None
            ),
        ),
    )
