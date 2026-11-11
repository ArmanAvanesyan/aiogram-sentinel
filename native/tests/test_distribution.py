"""Run against the installed companion wheel, never the source Python directory."""

from importlib.metadata import distribution

import aiogram_idle_native as native


def test_version_abi_and_independent_metadata():
    dist = distribution("aiogram-idle-native")
    assert dist.version == native.ENGINE_VERSION == "0.3.0"
    assert native.API_VERSION == 1
    assert not dist.requires
    assert native.DeadlineCore().keys() == []


def test_companion_is_a_compiled_extension():
    from aiogram_idle_native import _aiogram_idle_native

    assert _aiogram_idle_native.__file__.endswith((".so", ".pyd"))
    assert native.phase_transition("active", "due_prompt") == "prompt_pending"
