"""Pyperf-managed deterministic-kernel probes against the installed distribution.

Set AIOGRAM_NAV_BENCH_ENGINE=python|rust. Pyperf owns worker processes, warmups,
calibration and JSON output; this script never inserts the repository's src path.
"""

import inspect
import os
from importlib.metadata import version

import pyperf

from aiogram_nav import NavigationIntent, NavigationRegistry, Node
from aiogram_nav.codec import decode, encode

engine = os.environ.get("AIOGRAM_NAV_BENCH_ENGINE", "python")
if engine not in ("python", "rust"):
    raise SystemExit("AIOGRAM_NAV_BENCH_ENGINE must be python or rust")
if engine == "rust" and "engine" not in inspect.signature(decode).parameters:
    raise SystemExit("The published baseline does not implement the Rust engine")
raw = encode(NavigationIntent("benchmark", "main", {"values": [1, 2, 3], "label": "Հայերեն 😀"}))
decode_kwargs = {"engine": engine} if "engine" in inspect.signature(decode).parameters else {}
nodes = [Node("main", renderer="screen")]
nodes.extend(
    Node(f"n{i}", parent="main" if i == 0 else f"n{i - 1}", renderer="screen") for i in range(499)
)
registry_kwargs = (
    {"engine": engine} if "engine" in inspect.signature(NavigationRegistry).parameters else {}
)


def decode_once():
    return decode(raw, **decode_kwargs)


def registry_once():
    return NavigationRegistry(roots={"main"}, nodes=nodes, **registry_kwargs)


runner = pyperf.Runner()
runner.metadata["engine"] = engine
runner.metadata["installed_version"] = version("aiogram-nav")
runner.bench_func("nav_codec_decode", decode_once)
runner.bench_func("nav_registry_compile_500", registry_once)
