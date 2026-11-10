"""Examples must construct all advertised variants without Telegram access."""

from __future__ import annotations

import argparse
import logging
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from aiogram import Bot

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo.py"


@pytest.mark.parametrize("controls", ["reply", "inline", "commands", "hybrid"])
@pytest.mark.parametrize("fsm", [False, True])
async def test_demo_variants_construct_without_network(controls: str, fsm: bool) -> None:
    module = runpy.run_path(str(DEMO))
    args = argparse.Namespace(controls=controls, fsm=fsm, after=15.0, grace=30.0)
    async with Bot("123456:example-token") as bot:
        dispatcher, runtime = module["build_demo"](bot, args)
        assert runtime.namespace == "idle-demo"
        assert runtime.config.enabled
        assert runtime.policies["draft"].controls == controls
        assert dispatcher.get("_aiogram_idle_installed")


def test_example_help_does_not_require_a_bot_token() -> None:
    env = dict(os.environ)
    env.pop("BOT_TOKEN", None)
    result = subprocess.run(
        [sys.executable, str(DEMO), "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "--controls" in result.stdout
    assert "--fsm" in result.stdout


def test_importing_demo_does_not_configure_global_logging(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: calls.append(kwargs))
    runpy.run_path(str(DEMO))
    assert calls == []
