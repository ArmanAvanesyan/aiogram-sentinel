"""Public, application-positionable navigation bindings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Bot, Router
from aiogram.types import CallbackQuery, Message, Update

from .errors import ConfigurationError
from .inputs.bindings import CallbackEntry, CommandEntry, MatchedEntry, ReplyEntry

if TYPE_CHECKING:
    from .context import NavigationContext
    from .navigation import Navigation


def create_bindings_router(navigation: Navigation) -> Router:
    """Build controls without attaching or reordering any application router.

    Include this router at the chosen position before calling ``install`` with
    ``bindings_mode='manual'`` and this same router.
    """
    from .integration import CallbackFilter, EntryFilter, dispatch_action, handle_callback

    if navigation.installed:
        raise ConfigurationError("Create the bindings router before installing navigation")
    if navigation.bindings_router is not None:
        raise ConfigurationError("A bindings router already exists for this runtime")
    bindings = navigation.bindings
    if bindings is None:
        raise ConfigurationError("Configure input bindings before creating their router")
    bindings.validate(navigation.registry)
    router = Router(name="aiogram-nav")
    if any(isinstance(entry, (CommandEntry, ReplyEntry)) for entry in bindings.entries):

        async def entry_handler(
            message: Message,
            nav_context: NavigationContext,
            nav_match: MatchedEntry,
            event_update: Update,
        ) -> None:
            nav_context.control_handled = True
            await dispatch_action(
                nav_context,
                nav_match.action,
                source=nav_match.source,
                operation_id=f"update:{event_update.update_id}:nav:{nav_match.entry.id}",
            )

        router.message.register(entry_handler, EntryFilter(navigation))
    if any(isinstance(entry, CallbackEntry) for entry in bindings.entries):

        async def callback_handler(
            callback: CallbackQuery,
            nav_context: NavigationContext,
            bot: Bot,
            event_update: Update,
        ) -> None:
            nav_context.control_handled = True
            await handle_callback(navigation, callback, nav_context, bot, event_update.update_id)

        router.callback_query.register(callback_handler, CallbackFilter())
    navigation.register_bindings_router(router)
    return router
