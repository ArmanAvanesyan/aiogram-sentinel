"""Prepare opaque callback bindings before rendering their keyboard."""

from __future__ import annotations

import re
import secrets
from typing import Protocol

from ..errors import ConfigurationError
from ..models import ConversationKey, NavigationAction, NavigationToken

_TOKEN = re.compile(r"[A-Za-z0-9_-]{16,48}\Z")


class TokenRepository(Protocol):
    async def reserve_token(
        self, key: ConversationKey, token: NavigationToken, *, operation_id: str
    ) -> NavigationToken: ...


def parse_callback_data(data: str) -> str | None:
    if not data.startswith("nav:") or len(data.encode()) > 64:
        return None
    token = data[4:]
    return token if _TOKEN.fullmatch(token) else None


async def prepare_token(
    repository: TokenRepository,
    key: ConversationKey,
    *,
    session_id: str,
    view_id: str,
    action: NavigationAction,
    expires_at: int,
    operation_id: str,
    token: str | None = None,
    entry_id: str | None = None,
) -> str:
    candidate = token or secrets.token_urlsafe(24)
    if not _TOKEN.fullmatch(candidate):
        raise ConfigurationError("Callback tokens must be opaque URL-safe values")
    reserved = await repository.reserve_token(
        key,
        NavigationToken(
            candidate, key, key.user_id, session_id, view_id, action, expires_at, entry_id
        ),
        operation_id=operation_id,
    )
    # Deduplication may return an earlier random candidate for this logical action.
    if not _TOKEN.fullmatch(reserved.token):
        raise ConfigurationError("Repository returned an incompatible callback token")
    return f"nav:{reserved.token}"
