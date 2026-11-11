"""Build immutable menus without Telegram credentials or optional dependencies."""

from aiogram_cmds import (
    CmdsConfig,
    CommandDef,
    ProfileDef,
    ProfileRequest,
    build_profile_batch,
    compile_config,
)

config = CmdsConfig(
    languages=["en", "ru", "hy"],
    commands={
        "start": CommandDef(descriptions={"en": "Start", "ru": "Начать", "hy": "Սկսել"})
    },
    profiles={"member": ProfileDef(include=["start"])},
)
snapshot = compile_config(config, config_revision="menus-v1")
payloads = build_profile_batch(
    snapshot,
    [
        ProfileRequest("member", locale, 123, '{"type":"chat","chat_id":42}', None)
        for locale in ("en", "ru", "hy")
    ],
)
for payload in payloads:
    print(payload.commands, payload.fingerprint)
