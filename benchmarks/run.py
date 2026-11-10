"""Installed-package CPU/latency evidence; no repository source-path injection.

Use pyperf_suite.py for subprocess/calibrated pyperf Runner measurements. This
serial driver records explicit CPU, wall p95, RSS and call counters and writes a
pyperf-compatible suite alongside its detailed evidence. Run qualification with
no other builds/tests active; --quick is exploratory only.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import math
import os
import platform
import random
import statistics
import subprocess
import time
from importlib.metadata import version
from pathlib import Path

import orjson
import psutil
import pyperf

import aiogram_cmds as cmds
from aiogram_cmds.builders_configured import build_from_config
from aiogram_cmds.delivery import payload_fingerprint
from aiogram_cmds.registry import CommandRegistry

SEED = 1729
SCOPE = {"chat_id": 42, "type": "chat"}


class FakeBot:
    id = 123

    def __init__(self, delay: float = 0):
        self.calls = 0
        self.delay = delay

    async def set_my_commands(self, *args, **kwargs):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return True


def config(size: int, profiles: int = 1):
    names = [f"command_{index}" for index in range(size)]
    return cmds.CmdsConfig(
        languages=["en", "ru", "hy"],
        commands={name: cmds.CommandDef(i18n_key=f"{name}.desc") for name in names},
        profiles={
            f"profile_{index}": cmds.ProfileDef(include=names)
            for index in range(profiles)
        },
    )


def workloads(engine: str, quick: bool):
    supports = "engine" in inspect.signature(cmds.CommandScopeManager).parameters
    if engine == "rust" and not supports:
        raise RuntimeError("The published baseline has no Rust engine")
    engine_kw = {"engine": engine} if supports else {}
    hash_kw = (
        {"engine": engine}
        if "engine" in inspect.signature(payload_fingerprint).parameters
        else {}
    )
    items = []
    for size in (1, 10, 100):
        cfg = config(size)
        reg = CommandRegistry(cfg)
        counters = {"translator": 0}

        def translate(key, *, locale=None, _counters=counters, **kwargs):
            _counters["translator"] += 1
            return f"{locale}: {key} description"

        def render(_reg=reg, _translate=translate, _hash_kw=hash_kw):
            commands = build_from_config(
                _reg,
                _reg.resolve_profile_commands("profile_0"),
                lang="hy",
                translator=_translate,
                key_prefix="cmd",
            )
            return payload_fingerprint(123, SCOPE, None, commands, **_hash_kw)

        def comparator(_reg=reg, _translate=translate):
            commands = build_from_config(
                _reg,
                _reg.resolve_profile_commands("profile_0"),
                lang="hy",
                translator=_translate,
                key_prefix="cmd",
            )
            data = {
                "bot_id": 123,
                "scope": SCOPE,
                "language_code": None,
                "commands": [
                    {"command": c.command, "description": c.description}
                    for c in commands
                ],
            }
            return hashlib.sha256(
                orjson.dumps(data, option=orjson.OPT_SORT_KEYS)
            ).hexdigest()

        assert render() == comparator()
        names = reg.resolve_profile_commands("profile_0")
        rendered = build_from_config(
            reg, names, lang="hy", translator=translate, key_prefix="cmd"
        )

        def resolve(_reg=reg):
            if engine == "rust":
                from aiogram_cmds.engines import native_engine

                native = native_engine("rust")
                profile = _reg.cfg.profiles["profile_0"]
                return native.resolve_profile(
                    profile.include, profile.exclude, list(_reg.cfg.commands)
                )
            return _reg.resolve_profile_commands("profile_0")

        items.extend(
            [
                (
                    f"profile_resolution/{size}",
                    resolve,
                    200,
                    {},
                    False,
                ),
                (f"render_and_fingerprint/{size}", render, 30, counters, False),
                (f"orjson_comparator/{size}", comparator, 30, counters, False),
                (
                    f"resolved_fingerprint/{size}",
                    lambda _rows=rendered: payload_fingerprint(
                        123, SCOPE, None, _rows, **hash_kw
                    ),
                    100,
                    {},
                    False,
                ),
            ]
        )
        bot = FakeBot(delay=0.001)
        manager = cmds.CommandScopeManager(
            bot, config=cfg, translator=translate, **engine_kw
        )
        items.append(
            (
                f"fake_telegram_1ms/{size}",
                lambda _manager=manager: asyncio.run(
                    _manager.apply_profile(
                        42, "profile_0", language="hy", language_code=None
                    )
                ),
                1,
                {"bot": bot},
                False,
            )
        )
        hit_bot = FakeBot()
        hit_manager = cmds.CommandScopeManager(
            hit_bot, config=cfg, translator=translate, **engine_kw
        )
        confirmed = asyncio.run(
            hit_manager.apply_profile(
                42, "profile_0", language="hy", language_code=None
            )
        ).confirmed_fingerprint
        items.append(
            (
                f"confirmation_hit/{size}",
                lambda _manager=hit_manager, _hash=confirmed: asyncio.run(
                    _manager.apply_profile(
                        42,
                        "profile_0",
                        language="hy",
                        language_code=None,
                        previous_fingerprint=_hash,
                    )
                ),
                10,
                {"bot": hit_bot},
                False,
            )
        )
        if not hasattr(cmds, "compile_config"):
            continue
        for profiles in (1, 10, 100):
            snapshot = cmds.compile_config(
                config(size, profiles),
                config_revision="fixture-v1",
                translator=translate,
                translation_revision="static-v1",
                **engine_kw,
            )
            requests = [
                cmds.ProfileRequest(
                    f"profile_{index % profiles}", locale, 123, json.dumps(SCOPE), None
                )
                for index in range(10)
                for locale in ("en", "ru", "hy")
            ]

            def batch(_snapshot=snapshot, _requests=requests):
                return cmds.build_profile_batch(_snapshot, _requests, **engine_kw)

            items.append(
                (
                    f"compiled_batch/{size}/{profiles}_profiles/30_targets",
                    batch,
                    10,
                    counters,
                    True,
                )
            )
        mutable = config(size)
        revision = {"value": 0}

        def mutation(_cfg=mutable, _revision=revision, _translate=translate):
            _revision["value"] += 1
            _cfg.profiles["profile_0"].include.reverse()
            _cfg.commands["command_0"].descriptions = {
                "en": f"Revision {_revision['value']}"
            }

            def revised_translation(key, **kwargs):
                return f"{_translate(key, **kwargs)} revision {_revision['value']}"

            return cmds.compile_config(
                _cfg,
                config_revision=str(_revision["value"]),
                translator=revised_translation,
                translation_revision=str(_revision["value"]),
                **engine_kw,
            )

        items.append((f"explicit_recompile/{size}", mutation, 1, counters, True))
    return items


def sample(name, function, loops, counters, samples, warmups):
    if "fake_telegram" in name or "explicit_recompile" in name:
        loops = 1
    for _ in range(warmups):
        for _ in range(loops):
            function()
    translator_before = counters.get("translator", 0)
    bot = counters.get("bot")
    bot_before = bot.calls if bot else 0
    wall, cpu = [], []
    individual = []
    for _ in range(samples):
        start_cpu = time.process_time_ns()
        start_wall = time.perf_counter_ns()
        for _ in range(loops):
            function()
        wall.append((time.perf_counter_ns() - start_wall) / loops)
        cpu.append((time.process_time_ns() - start_cpu) / loops)
    if "fake_telegram" in name or "confirmation_hit" in name:
        for _ in range(100 if samples == 5 else 1000):
            started = time.perf_counter_ns()
            function()
            individual.append(time.perf_counter_ns() - started)
    return {
        "individual_latency_ns": {
            "count": len(individual),
            "p95": sorted(individual)[math.ceil(0.95 * len(individual)) - 1]
            if individual
            else None,
        },
        "loops": loops,
        "samples": samples,
        "warmups": warmups,
        "wall_ns": {
            "median": statistics.median(wall),
            "p95": sorted(wall)[math.ceil(len(wall) * 0.95) - 1],
            "values": wall,
        },
        "cpu_ns": {
            "median": statistics.median(cpu),
            "p95": sorted(cpu)[math.ceil(len(cpu) * 0.95) - 1],
            "values": cpu,
        },
        "rss_bytes": psutil.Process().memory_info().rss,
        "calls": {
            "translator": counters.get("translator", 0) - translator_before,
            "telegram": (bot.calls - bot_before) if bot else 0,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["python", "rust"], default="python")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    random.seed(SEED)
    published = version("aiogram-cmds") == "0.2.0"
    commit = "published-0.2.0"
    if not published:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        ).strip()
    try:
        rust_version = subprocess.run(
            ["rustc", "--version"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except FileNotFoundError:
        rust_version = None
    metadata = {
        "package": "aiogram-cmds",
        "package_version": version("aiogram-cmds"),
        "engine": args.engine,
        "commit": commit,
        "installed_module": cmds.__file__,
        "python": platform.python_version(),
        "rust": rust_version,
        "os": platform.platform(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "seed": SEED,
        "protocol": "serial-inprocess-v1",
        "exploratory": args.quick,
        "notes": "CPU excludes fake network delay; wall p95 includes it only in separately named fake_telegram workloads. New compiled APIs are not baseline-comparable.",
    }
    results, pyperf_benchmarks = {}, []
    for name, function, loops, counters, new_only in workloads(args.engine, args.quick):
        result = sample(
            name,
            function,
            loops,
            counters,
            5 if args.quick else 31,
            1 if args.quick else 5,
        )
        result["new_only"] = new_only
        results[name] = result
        values = [value / 1e9 for value in result["wall_ns"]["values"]]
        pyperf_benchmarks.append(
            pyperf.Benchmark(
                [
                    pyperf.Run(
                        values,
                        metadata={"name": name, "engine": args.engine, "loops": 1},
                        collect_metadata=True,
                    )
                ]
            )
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"metadata": metadata, "benchmarks": results}, indent=2) + "\n"
    )
    pyperf_path = args.output.with_suffix(".pyperf.json")
    pyperf.BenchmarkSuite(pyperf_benchmarks).dump(str(pyperf_path), replace=True)
    print(args.output)


if __name__ == "__main__":
    main()
