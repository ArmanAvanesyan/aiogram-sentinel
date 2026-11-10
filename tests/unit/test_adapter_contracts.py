"""Regression tests for typed boundaries to Telegram and i18n adapters."""

from contextlib import contextmanager
from unittest.mock import AsyncMock

import pytest

from aiogram_cmds.apply import apply_config
from aiogram_cmds.customize import CmdsConfig, ScopeDef
from aiogram_cmds.translator import build_translator_from_i18n


class AiogramStyleI18n:
    """Match aiogram's combined singular/plural gettext interface."""

    def __init__(self):
        self.locale = "en"

    @contextmanager
    def with_locale(self, locale):
        previous = self.locale
        self.locale = locale
        try:
            yield
        finally:
            self.locale = previous

    def gettext(self, singular, plural=None, n=1):
        chosen = plural if plural is not None and n != 1 else singular
        return f"{self.locale}:{chosen}"


def test_aiogram_plural_gettext_and_locale_restoration():
    adapter = AiogramStyleI18n()
    translate = build_translator_from_i18n(adapter)
    assert translate("file", plural="files", count=2, locale="ru") == "ru:files"
    assert translate("file", plural="files", count=1) == "en:file"
    assert adapter.locale == "en"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope,chat_id,user_id",
    [
        ("chat", None, None),
        ("chat_admins", None, None),
        ("chat_member", None, 42),
        ("chat_member", 42, None),
    ],
)
async def test_missing_scope_identity_fails_before_telegram(scope, chat_id, user_id):
    bot = AsyncMock()
    cfg = CmdsConfig(
        scopes=[
            ScopeDef(scope=scope, profile="default", chat_id=chat_id, user_id=user_id)
        ]
    )
    with pytest.raises(ValueError, match="require"):
        await apply_config(bot, cfg)
    bot.set_my_commands.assert_not_called()
    bot.set_chat_menu_button.assert_not_called()
