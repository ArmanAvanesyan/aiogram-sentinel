"""Invalid opt-in configuration must not accidentally exempt traffic."""

import pytest
from aiogram.types import Message, MessageEntity

from aiogram_sentinel import (
    ActionPolicy,
    DebounceCfg,
    ErrorConfig,
    SentinelConfig,
    SentinelExemptions,
    ThrottleCfg,
)
from aiogram_sentinel.actions import classify_action
from aiogram_sentinel.exceptions import ConfigurationError


@pytest.mark.parametrize(
    "kwargs",
    [
        {"commands": "start"},
        {"callback_prefixes": "safe:"},
        {"commands": ("/start",)},
        {"commands": ("start@bot",)},
        {"commands": (1,)},
        {"callback_prefixes": ("",)},
        {"callback_prefixes": ("a" * 65,)},
        {"callback_prefixes": (None,)},
    ],
)
def test_exemption_misconfiguration_fails_closed(kwargs):
    with pytest.raises(ConfigurationError):
        SentinelExemptions(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bucket_mode": "command_text"},
        {"action_policies": None},
        {"action_policies": {"other": ActionPolicy()}},
        {"action_policies": {"message": None}},
        {"exemptions": ()},
    ],
)
def test_action_configuration_rejects_unknown_modes_and_shapes(kwargs):
    with pytest.raises(ConfigurationError):
        SentinelConfig(**kwargs)


@pytest.mark.parametrize("kwargs", [{"throttle": 1}, {"debounce": "disabled"}])
def test_action_policy_reuses_typed_policy_contracts(kwargs):
    with pytest.raises(ConfigurationError):
        ActionPolicy(**kwargs)


@pytest.mark.parametrize("types", [[TimeoutError], (BaseException,), ("RedisError",)])
def test_passthrough_configuration_accepts_only_exception_types(types):
    with pytest.raises(ValueError):
        ErrorConfig(reraise_exceptions=types)


def test_stored_configuration_is_defensively_copied():
    policies = {"message": ActionPolicy(ThrottleCfg(2, 60), DebounceCfg(4))}
    commands, prefixes = ["START"], ["safe:"]
    exemptions = SentinelExemptions(commands=commands, callback_prefixes=prefixes)
    cfg = SentinelConfig(action_policies=policies, exemptions=exemptions)
    policies.clear()
    commands.append("menu")
    prefixes.clear()
    assert cfg.action_policies["message"].throttle.rate == 2
    assert cfg.exemptions.commands == ("start",)
    assert cfg.exemptions.callback_prefixes == ("safe:",)
    with pytest.raises(TypeError):
        cfg.action_policies["command"] = ActionPolicy()


def test_slash_text_without_a_command_entity_is_an_ordinary_message():
    message = Message.model_validate(
        {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": 42, "type": "private"},
            "text": "/start",
        }
    )
    assert classify_action(message) == "message"
    assert not SentinelExemptions(commands=("start",)).matches(message)
    actual = message.model_copy(
        update={"entities": [MessageEntity(type="bot_command", offset=0, length=6)]}
    )
    assert classify_action(actual) == "command"
    assert SentinelExemptions(commands=("start",)).matches(actual)
