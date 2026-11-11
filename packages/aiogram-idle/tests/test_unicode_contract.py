"""All public persistent inputs use strict Unicode scalars, without normalization."""

import pytest

from aiogram_idle import IdleConversationKey
from aiogram_idle.errors import ConfigurationError
from aiogram_idle.models import SessionSnapshot, freeze_object
from aiogram_idle.registration import ActivityRegistration


@pytest.mark.parametrize("text", ["\ud800", "\udfff", "\ud83d\ude42"])
def test_non_utf8_identifiers_and_json_are_rejected_early(text):
    for construct in (
        lambda: IdleConversationKey(text, 1, 42, 42),
        lambda: SessionSnapshot(text, 2000),
        lambda: ActivityRegistration(text, "policy", "adapter"),
        lambda: freeze_object({"value": text}),
        lambda: freeze_object({text: "value"}),
    ):
        with pytest.raises(ConfigurationError):
            construct()


def test_valid_unicode_is_preserved_without_normalization():
    value = "🙂 e\u0301 é Հայաստան"
    assert IdleConversationKey(value, 1, 42, 42).namespace == value
    assert freeze_object({"value": value})["value"] == value
