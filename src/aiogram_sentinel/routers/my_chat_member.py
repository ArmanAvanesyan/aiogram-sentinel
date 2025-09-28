"""Membership router for aiogram-sentinel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..storage.base import BlocklistBackend


def make_sentinel_router(
    blocklist_backend: BlocklistBackend,
    on_block: Callable[[int, str, dict[str, Any]], Awaitable[Any]] | None = None,
    on_unblock: Callable[[int, str, dict[str, Any]], Awaitable[Any]] | None = None,
) -> Router:
    """Create a router that handles my_chat_member updates to sync blocklist.

    Args:
        blocklist_backend: Blocklist backend instance
        on_block: Optional hook called when user is blocked
        on_unblock: Optional hook called when user is unblocked

    Returns:
        Router configured to handle my_chat_member updates
    """
    router = Router()

    @router.my_chat_member()
    async def _handle_my_chat_member(event: ChatMemberUpdated) -> None:  # type: ignore
        """Handle my_chat_member updates to sync blocklist."""
        # Only handle private chats
        if event.chat.type != "private":
            return

        # Extract user information
        user = event.from_user
        if not user:
            return

        user_id = user.id
        username = user.username or ""

        # Determine membership state transition
        old_status = event.old_chat_member.status
        new_status = event.new_chat_member.status

        # Handle state transitions
        if _should_block_user(old_status, new_status):
            # User was kicked/left -> block them
            await blocklist_backend.set_blocked(user_id, True)

            # Call on_block hook if provided
            if on_block:
                try:
                    await on_block(
                        user_id,
                        username,
                        {
                            "old_status": old_status,
                            "new_status": new_status,
                            "user": user,
                            "chat": event.chat,
                        },
                    )
                except Exception:
                    # Log error but don't fail the router
                    pass

        elif _should_unblock_user(old_status, new_status):
            # User became member from kicked/left -> unblock them
            await blocklist_backend.set_blocked(user_id, False)

            # Call on_unblock hook if provided
            if on_unblock:
                try:
                    await on_unblock(
                        user_id,
                        username,
                        {
                            "old_status": old_status,
                            "new_status": new_status,
                            "user": user,
                            "chat": event.chat,
                        },
                    )
                except Exception:
                    # Log error but don't fail the router
                    pass

    return router


def _should_block_user(old_status: str, new_status: str) -> bool:
    """Determine if user should be blocked based on status transition."""
    # Block if user was kicked or left
    return new_status in {"kicked", "left"}


def _should_unblock_user(old_status: str, new_status: str) -> bool:
    """Determine if user should be unblocked based on status transition."""
    # Unblock if user became member from kicked or left
    return new_status == "member" and old_status in {"kicked", "left"}


def create_block_hook(
    callback: Callable[[int, str, dict[str, Any]], Awaitable[Any]],
) -> Callable[[int, str, dict[str, Any]], Awaitable[Any]]:
    """Create a block hook with error handling."""

    async def hook(user_id: int, username: str, data: dict[str, Any]) -> None:
        """Block hook with error handling."""
        try:
            await callback(user_id, username, data)
        except Exception:
            # Log error but don't fail the router
            pass

    return hook


def create_unblock_hook(
    callback: Callable[[int, str, dict[str, Any]], Awaitable[Any]],
) -> Callable[[int, str, dict[str, Any]], Awaitable[Any]]:
    """Create an unblock hook with error handling."""

    async def hook(user_id: int, username: str, data: dict[str, Any]) -> None:
        """Unblock hook with error handling."""
        try:
            await callback(user_id, username, data)
        except Exception:
            # Log error but don't fail the router
            pass

    return hook
