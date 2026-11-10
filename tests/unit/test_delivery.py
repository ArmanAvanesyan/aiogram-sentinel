"""Explicit menu slots, caller confirmations and partial network effects."""

import asyncio
from dataclasses import FrozenInstanceError

import pytest
from aiogram.types import BotCommandScopeChat

from aiogram_cmds import (
    UNSET,
    CommandScopeManager,
    ScopeDef,
    apply_config,
    apply_config_result,
    clear_language_variants,
    set_user_profile,
)


@pytest.mark.parametrize(
    "slot,expected", [(UNSET, "ru"), (None, None), ("", None), ("hy", "hy")]
)
async def test_rendering_locale_is_independent_of_menu_slot(
    mock_bot, basic_config, slot, expected
):
    def translator(key, **kwargs):
        return f"{kwargs['locale']} description"

    await set_user_profile(
        mock_bot,
        basic_config,
        translator=translator,
        user_id=42,
        chat_id=None,
        profile="user",
        language="ru",
        language_code=slot,
    )
    call = mock_bot.set_my_commands.call_args
    assert call.args[0][0].description == "ru description"
    if expected is None:
        assert "language_code" not in call.kwargs
    else:
        assert call.kwargs["language_code"] == expected


async def test_scope_override_and_global_single_list(mock_bot, basic_config):
    basic_config.per_language = False
    basic_config.scopes.append(
        ScopeDef(scope="chat", chat_id=42, profile="user", per_language=True)
    )
    await apply_config(mock_bot, basic_config)
    calls = mock_bot.set_my_commands.call_args_list
    global_calls = [c for c in calls if c.kwargs["scope"].type == "all_private_chats"]
    private_calls = [c for c in calls if c.kwargs["scope"].type == "chat"]
    assert len(global_calls) == 1 and "language_code" not in global_calls[0].kwargs
    assert [c.kwargs["language_code"] for c in private_calls] == ["en", "ru"]


async def test_confirmation_and_redundant_call_suppression(mock_bot, basic_config):
    mock_bot.id = 123
    manager = CommandScopeManager(mock_bot, config=basic_config)
    first = await manager.apply_profile(42, "user", language_code=None)
    assert (
        first.status == "applied" and first.confirmed_fingerprint == first.fingerprint
    )
    second = await manager.apply_profile(
        42, "user", language_code=None, previous_fingerprint=first.confirmed_fingerprint
    )
    assert second.status == "unchanged"
    assert second.confirmed_fingerprint == first.confirmed_fingerprint
    assert mock_bot.set_my_commands.await_count == 1
    with pytest.raises(FrozenInstanceError):
        first.status = "failed"


@pytest.mark.parametrize(
    "change", ["bot", "actor", "chat", "language_slot", "description", "order"]
)
async def test_fingerprint_covers_complete_payload(mock_bot, basic_config, change):
    mock_bot.id = 123
    manager = CommandScopeManager(mock_bot, config=basic_config)
    first = await manager.apply_profile(42, "user")
    user_id, chat_id, code = 42, None, UNSET
    if change == "bot":
        mock_bot.id = 124
    if change == "actor":
        user_id = 43
    if change == "chat":
        chat_id = 99
    if change == "language_slot":
        code = None
    if change == "description":
        basic_config.commands["start"].descriptions["en"] = "New description"
    if change == "order":
        basic_config.profiles["user"].include.reverse()
    second = await manager.apply_profile(
        user_id,
        "user",
        chat_id=chat_id,
        language_code=code,
        previous_fingerprint=first.confirmed_fingerprint,
    )
    assert second.status == "applied" and second.fingerprint != first.fingerprint
    assert mock_bot.set_my_commands.await_count == 2


async def test_failures_never_confirm_even_ambiguous_or_false(mock_bot, basic_config):
    mock_bot.id = 123
    error = TimeoutError("response lost")
    mock_bot.set_my_commands.side_effect = error
    manager = CommandScopeManager(mock_bot, config=basic_config, best_effort=True)
    result = await manager.apply_profile(42, "user")
    assert result.status == "failed" and result.error is error
    assert result.confirmed_fingerprint is None
    mock_bot.set_my_commands.side_effect = None
    mock_bot.set_my_commands.return_value = False
    assert (await manager.apply_profile(42, "user")).status == "failed"


async def test_original_errors_and_external_cancellation_propagate(
    mock_bot, basic_config
):
    mock_bot.id = 123
    error = RuntimeError("network")
    mock_bot.set_my_commands.side_effect = error
    with pytest.raises(RuntimeError) as caught:
        await CommandScopeManager(mock_bot, config=basic_config).apply_profile(
            42, "user"
        )
    assert caught.value is error
    mock_bot.set_my_commands.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await CommandScopeManager(
            mock_bot, config=basic_config, best_effort=True
        ).apply_profile(42, "user")


async def test_partial_batch_retains_only_confirmed_targets(mock_bot, basic_config):
    error = RuntimeError("second scope rejected")
    mock_bot.set_my_commands.side_effect = [True, error]
    result = await apply_config_result(mock_bot, basic_config, best_effort=True)
    assert result.status == "partial" and len(result.completed_targets) == 1
    assert result.failed_target and result.error is error
    mock_bot.set_chat_menu_button.assert_not_called()


async def test_menu_button_failure_is_partial_and_default_errors_original(
    mock_bot, basic_config
):
    error = RuntimeError("menu rejected")
    mock_bot.set_chat_menu_button.side_effect = error
    manager = CommandScopeManager(mock_bot, config=basic_config, best_effort=True)
    result = await manager.apply_all()
    assert result.status == "partial" and len(result.completed_targets) == 2
    assert result.failed_target == "menu_button"
    with pytest.raises(RuntimeError) as caught:
        await apply_config(mock_bot, basic_config)
    assert caught.value is error


async def test_only_explicit_language_variants_are_deleted(mock_bot):
    await clear_language_variants(
        mock_bot, user_id=42, language_codes=["en", "ru", "hy", "ru"]
    )
    assert [
        c.kwargs["language_code"] for c in mock_bot.delete_my_commands.call_args_list
    ] == ["en", "ru", "hy"]
    assert all(
        c.kwargs["scope"] == BotCommandScopeChat(chat_id=42)
        for c in mock_bot.delete_my_commands.call_args_list
    )


@pytest.mark.parametrize("codes", [["ru", ""], "ru", [None]])
async def test_invalid_cleanup_is_rejected_before_any_effect(mock_bot, codes):
    with pytest.raises((ValueError, TypeError)):
        await clear_language_variants(mock_bot, user_id=42, language_codes=codes)
    mock_bot.delete_my_commands.assert_not_called()


async def test_invalid_fingerprint_rejected_without_network(mock_bot, basic_config):
    mock_bot.id = 123
    with pytest.raises(ValueError, match="fingerprint"):
        await CommandScopeManager(mock_bot, config=basic_config).apply_profile(
            42, "user", previous_fingerprint=123
        )
    mock_bot.set_my_commands.assert_not_called()


async def test_real_catalogs_three_locales_restore_context(tmp_path):
    from gettext import GNUTranslations

    from aiogram.utils.i18n import I18n
    from babel.messages.catalog import Catalog
    from babel.messages.mofile import write_mo

    from aiogram_cmds import build_translator_from_i18n

    messages = {
        "en": ("Start", "one file", "several files"),
        "ru": ("Начать", "файл", "файлы"),
        "hy": ("Սկսել", "ֆայլ", "ֆայլեր"),
    }
    for locale, (start, single, plural) in messages.items():
        catalog = Catalog(locale=locale)
        catalog.add("cmd.start.desc", start)
        count = catalog.num_plurals
        catalog.add(("file", "files"), tuple([single] + [plural] * (count - 1)))
        target = tmp_path / locale / "LC_MESSAGES" / "messages.mo"
        target.parent.mkdir(parents=True)
        with target.open("wb") as file:
            write_mo(file, catalog)
    i18n = I18n(path=tmp_path, default_locale="en", domain="messages")
    translate = build_translator_from_i18n(i18n)
    for locale, (start, _single, _plural) in messages.items():
        assert translate("cmd.start.desc", locale=locale) == start
        with (tmp_path / locale / "LC_MESSAGES" / "messages.mo").open("rb") as file:
            expected = GNUTranslations(file)
        for count in (1, 2, 5):
            assert translate(
                "file", plural="files", count=count, locale=locale
            ) == expected.ngettext("file", "files", count)
        assert i18n.current_locale == "en"


async def test_unknown_profile_never_clears_menu(mock_bot, basic_config):
    mock_bot.id = 123
    with pytest.raises(ValueError, match="Unknown command profile"):
        await CommandScopeManager(mock_bot, config=basic_config).apply_profile(
            42, "typo"
        )
    mock_bot.set_my_commands.assert_not_called()


@pytest.mark.parametrize("method", ["classic", "generic", "clear", "setup"])
async def test_legacy_boolean_wrappers_never_claim_false_api_result(
    mock_bot, basic_config, method
):
    mock_bot.set_my_commands.return_value = False
    mock_bot.delete_my_commands.return_value = False
    manager = CommandScopeManager(mock_bot, config=basic_config, best_effort=True)
    calls = {
        "classic": lambda: manager.update_user_commands(42, True, False),
        "generic": lambda: manager.update_profile(42, "user"),
        "clear": lambda: manager.clear_user_commands(42),
        "setup": manager.setup_all,
    }
    assert await calls[method]() is False


async def test_empty_and_none_slots_have_identical_confirmation(mock_bot, basic_config):
    mock_bot.id = 123
    manager = CommandScopeManager(mock_bot, config=basic_config)
    first = await manager.apply_profile(42, "user", language_code=None)
    assert (
        await manager.apply_profile(
            42,
            "user",
            language_code="",
            previous_fingerprint=first.confirmed_fingerprint,
        )
    ).status == "unchanged"


async def test_best_effort_cleanup_reports_failure_without_default_deletion(
    mock_bot, basic_config
):
    mock_bot.delete_my_commands.side_effect = [True, TimeoutError("lost response")]
    manager = CommandScopeManager(mock_bot, config=basic_config, best_effort=True)
    assert await manager.clear_language_variants(42, ["en", "ru"]) is False
    assert all(
        "language_code" in c.kwargs for c in mock_bot.delete_my_commands.call_args_list
    )


async def test_single_list_config_applies_to_generic_and_legacy_pushes(
    mock_bot, basic_config
):
    mock_bot.id = 123
    basic_config.per_language = False
    manager = CommandScopeManager(mock_bot, config=basic_config)
    assert await manager.update_profile(42, "user", language="ru")
    assert "language_code" not in mock_bot.set_my_commands.call_args.kwargs
    assert (await manager.apply_profile(42, "user", language="ru")).status == "applied"
    assert "language_code" not in mock_bot.set_my_commands.call_args.kwargs
    assert await manager.update_user_commands(42, True, False, user_language="ru")
    assert "language_code" not in mock_bot.set_my_commands.call_args.kwargs
    assert await manager.update_profile(42, "user", language="ru", language_code="hy")
    assert mock_bot.set_my_commands.call_args.kwargs["language_code"] == "hy"


async def test_batch_prevalidates_later_scope_before_any_effect(mock_bot, basic_config):
    basic_config.scopes.append(ScopeDef(scope="chat", profile="user"))
    result = await apply_config_result(mock_bot, basic_config, best_effort=True)
    assert result.status == "failed" and result.completed_targets == ()
    assert result.failed_target == "configuration"
    mock_bot.set_my_commands.assert_not_called()
    mock_bot.set_chat_menu_button.assert_not_called()


async def test_single_list_scope_overrides_global_setting(mock_bot, basic_config):
    basic_config.scopes[0].per_language = False
    await apply_config(mock_bot, basic_config)
    mock_bot.set_my_commands.assert_awaited_once()
    assert "language_code" not in mock_bot.set_my_commands.call_args.kwargs


async def test_batch_cancellation_never_becomes_best_effort_failure(
    mock_bot, basic_config
):
    mock_bot.set_my_commands.side_effect = [True, asyncio.CancelledError]
    with pytest.raises(asyncio.CancelledError):
        await apply_config_result(mock_bot, basic_config, best_effort=True)
    mock_bot.set_chat_menu_button.assert_not_called()


@pytest.mark.parametrize("response", [None, 0, 1, "ok"])
async def test_non_boolean_responses_never_confirm(mock_bot, basic_config, response):
    mock_bot.id = 123
    mock_bot.set_my_commands.return_value = response
    result = await CommandScopeManager(
        mock_bot, config=basic_config, best_effort=True
    ).apply_profile(42, "user")
    assert result.status == "failed" and result.confirmed_fingerprint is None
