"""Real aiogram registration, action policies and ancestor attachment."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, Update, User

from aiogram_sentinel import (
    ActionPolicy,
    DebounceCfg,
    Policy,
    Sentinel,
    SentinelConfig,
    SentinelExemptions,
    ThrottleCfg,
    debounce,
    policy,
    rate_limit,
    registry,
)


def update(number, text="message", *, command=False, callback=False):
    user = User(id=42, is_bot=False, first_name="Example")
    message = Message(
        message_id=number,
        date=datetime.now(timezone.utc),
        chat=Chat(id=42, type="private"),
        from_user=user,
        text=text,
        entities=(
            [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))]
            if command
            else None
        ),
    )
    return Update(
        update_id=number,
        message=None if callback else message,
        callback_query=(
            CallbackQuery(
                id=str(number),
                from_user=user,
                chat_instance="example",
                message=message,
                data=text,
            )
            if callback
            else None
        ),
    )


@pytest.mark.parametrize(
    "protection",
    ["named_throttle", "legacy_throttle", "named_debounce", "legacy_debounce"],
)
async def test_real_registered_callback_policies_and_data_reach_handler(protection):
    dp, root, child = Dispatcher(), Router(), Router()
    root.include_router(child)
    seen = []

    async def business(message: Message, **data):
        seen.append(data)

    if protection.startswith("named"):
        kind = "throttle" if protection.endswith("throttle") else "debounce"
        name = uuid4().hex
        cfg = ThrottleCfg(1, 60) if kind == "throttle" else DebounceCfg(60)
        registry.register(Policy(name, kind, cfg))
        business = policy(name)(business)
    elif protection.endswith("throttle"):
        business = rate_limit(1, 60)(business)
    else:
        business = debounce(60)(business)
    child.message.register(business)
    await Sentinel.setup(dp, SentinelConfig(), root)
    bot = Bot("123456:TEST")
    try:
        for index in (1, 2):
            # Throttle different bodies; debounce identical bodies.
            text = str(index) if protection.endswith("throttle") else "same"
            await dp.feed_update(bot, update(index, text))
        assert len(seen) == 1
        assert seen[0]["sentinel_action_kind"] == "message"
        key = (
            "sentinel_throttle_cfg"
            if protection.endswith("throttle")
            else "sentinel_debounce_cfg"
        )
        assert key in seen[0]
    finally:
        await bot.session.close()
        await dp.storage.close()


@pytest.mark.parametrize("ancestor", [True, False])
async def test_only_an_ancestor_protects_a_child_handler(ancestor, caplog):
    dp, app, child = Dispatcher(), Router(), Router()
    app.include_router(child)
    seen = []

    @child.message()
    async def business(message: Message):
        seen.append(message.text)

    cfg = SentinelConfig(throttling_default_max=1)
    if ancestor:
        await Sentinel.setup(dp, cfg, app)
    else:
        await Sentinel.setup(dp, cfg)
        dp.include_router(app)
    await dp.emit_startup()
    await dp.emit_startup()
    warnings = [r for r in caplog.records if "Sentinel protected router" in r.message]
    assert len(warnings) == (0 if ancestor else 1)
    bot = Bot("123456:TEST")
    try:
        await dp.feed_update(bot, update(1, "one"))
        await dp.feed_update(bot, update(2, "two"))
        assert len(seen) == (1 if ancestor else 2)
    finally:
        await bot.session.close()
        await dp.storage.close()


@pytest.mark.parametrize("bucket_mode,expected", [("shared", 1), ("action_kind", 3)])
async def test_action_kinds_split_only_when_requested(bucket_mode, expected):
    dp, router = Dispatcher(), Router()
    seen = []

    async def business(event, **data):
        seen.append(data["sentinel_action_kind"])

    router.message.register(business)
    router.callback_query.register(business)
    await Sentinel.setup(
        dp, SentinelConfig(throttling_default_max=1, bucket_mode=bucket_mode), router
    )
    bot = Bot("123456:TEST")
    try:
        await dp.feed_update(bot, update(1, "plain"))
        await dp.feed_update(bot, update(2, "/menu", command=True))
        await dp.feed_update(bot, update(3, "menu", callback=True))
        assert len(seen) == expected
    finally:
        await bot.session.close()
        await dp.storage.close()


async def test_action_policies_exemptions_and_application_guard():
    dp, router = Dispatcher(), Router()
    seen, guarded = [], []

    async def guard(handler, event, data):
        guarded.append(event)
        return await handler(event, data)

    router.message.middleware(guard)
    router.callback_query.middleware(guard)

    async def business(event):
        seen.append(event)

    router.message.register(business)
    router.callback_query.register(business)
    await Sentinel.setup(
        dp,
        SentinelConfig(
            action_policies={
                "message": ActionPolicy(throttle=ThrottleCfg(1, 60)),
                "callback_query": ActionPolicy(debounce=DebounceCfg(60)),
            },
            bucket_mode="action_kind",
            exemptions=SentinelExemptions(
                commands=("start",), callback_prefixes=("safe:",)
            ),
        ),
        router,
    )
    bot = Bot("123456:TEST")
    try:
        events = [
            update(1, "one"),
            update(2, "two"),
            update(3, "/start@ExampleBot", command=True),
            update(4, "/start@ExampleBot", command=True),
            update(5, "safe:menu", callback=True),
            update(6, "safe:menu", callback=True),
            update(7, "normal", callback=True),
            update(8, "normal", callback=True),
        ]
        for event in events:
            await dp.feed_update(bot, event)
        assert len(guarded) == 8  # Spam exemptions never skip application guards.
        assert len(seen) == 6
    finally:
        await bot.session.close()
        await dp.storage.close()


@pytest.mark.parametrize("legacy_override", [True, False])
async def test_filter_override_beats_named_and_action_defaults(legacy_override):
    from aiogram.filters import Filter

    class Override(Filter):
        async def __call__(self, message):
            if legacy_override:
                return {"sentinel_rate_limit": (2, 60)}
            return {"sentinel_throttle_cfg": ThrottleCfg(2, 60)}

    name = uuid4().hex
    registry.register(Policy(name, "throttle", ThrottleCfg(1, 60)))
    dp, router = Dispatcher(), Router()
    seen = []

    @router.message(Override())
    @policy(name)
    async def business(message: Message, sentinel_throttle_cfg):
        seen.append(sentinel_throttle_cfg.rate)

    await Sentinel.setup(
        dp,
        SentinelConfig(
            action_policies={"message": ActionPolicy(throttle=ThrottleCfg(3, 60))}
        ),
        router,
    )
    bot = Bot("123456:TEST")
    try:
        for index in (1, 2, 3):
            await dp.feed_update(bot, update(index, str(index)))
        assert seen == [2, 2]
    finally:
        await bot.session.close()
        await dp.storage.close()
