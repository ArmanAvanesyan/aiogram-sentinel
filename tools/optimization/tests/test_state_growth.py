"""State-growth measurements must not mislabel server subcommands as network calls."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "state_growth", Path(__file__).parents[1] / "benchmark_state_growth.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_resp_request_bytes_use_encoded_lengths_and_client_invocations():
    metrics = module.CommandMetrics()
    metrics.observe(("SET", "key", "é"))
    expected = b"*3\r\n$3\r\nSET\r\n$3\r\nkey\r\n$2\r\n\xc3\xa9\r\n"
    assert metrics.snapshot()["client_command_calls"] == 1
    assert metrics.snapshot()["command_argument_bytes"] == 8
    assert metrics.snapshot()["computed_resp_request_bytes"] == len(expected)
    metrics.observe(("EVAL", "redis.call('GET', KEYS[1])", 1, "key"))
    assert metrics.snapshot()["client_command_calls"] == 2
    assert metrics.snapshot()["command_histogram"] == {"SET": 1, "EVAL": 1}
    assert "GET" not in metrics.snapshot()["command_histogram"]


def test_composite_command_name_matches_resp_packaging():
    metrics = module.CommandMetrics()
    metrics.observe(("CLIENT SETINFO", "LIB-NAME", "redis-py"))
    expected = b"*4\r\n$6\r\nCLIENT\r\n$7\r\nSETINFO\r\n$8\r\nLIB-NAME\r\n$8\r\nredis-py\r\n"
    assert metrics.snapshot()["computed_resp_request_bytes"] == len(expected)


def test_state_inspection_commands_are_excluded():
    metrics = module.CommandMetrics()
    before = metrics.snapshot()
    with metrics.paused():
        metrics.observe(("SCAN", 0))
        with metrics.paused():
            metrics.observe(("MEMORY USAGE", "key"))
    assert metrics.snapshot() == before
    metrics.observe(("GET", "key"))
    assert metrics.snapshot()["client_command_calls"] == 1


@pytest.mark.asyncio
async def test_redis_execute_command_wrapper_counts_api_calls(monkeypatch):
    redis = pytest.importorskip("redis.asyncio")

    async def execute(self, *args, **kwargs):
        return b"value"

    monkeypatch.setattr(redis.Redis, "execute_command", execute)
    metrics = module.CommandMetrics()
    client = module.counting_redis("redis://127.0.0.1:1/0", metrics)
    assert await client.get("key") == b"value"
    assert metrics.snapshot()["client_command_calls"] == 1
    assert metrics.snapshot()["command_histogram"] == {"GET": 1}
    await client.aclose()


@pytest.mark.asyncio
async def test_pipeline_commands_are_not_execute_command_invocations(monkeypatch):
    redis = pytest.importorskip("redis.asyncio")

    class FakePipeline:
        def __init__(self):
            self.command_stack = [(("GET", "key"), {}), (("SET", "key", "value"), {})]

        async def execute(self):
            return [b"value", True]

    monkeypatch.setattr(redis.Redis, "pipeline", lambda *args, **kwargs: FakePipeline())
    metrics = module.CommandMetrics()
    client = module.counting_redis("redis://127.0.0.1:1/0", metrics)
    assert await client.pipeline().execute() == [b"value", True]
    row = metrics.snapshot()
    assert row["client_command_calls"] == 0
    assert row["pipeline_execute_calls"] == 1
    assert row["command_histogram"] == {"MULTI": 1, "GET": 1, "SET": 1, "EXEC": 1}
    await client.aclose()


def test_public_fixtures_do_not_inject_checkouts_or_import_private_implementations():
    text = Path(module.__file__).read_text()
    assert "sys.path.insert" not in text
    assert "from tests" not in text
    assert '"qualification": False' in text


def test_baseline_engine_selection_does_not_silently_fallback():
    class BaselineConfig:
        def __init__(self, max_receipts=256):
            self.max_receipts = max_receipts

    assert module.config(BaselineConfig, engine="python").max_receipts == 256
    assert module.config(BaselineConfig, engine="python", max_receipts=6000).max_receipts == 6000
    with pytest.raises(RuntimeError, match="native engine"):
        module.config(BaselineConfig, engine="rust")


def test_candidate_engine_selection_is_explicit():
    class CandidateConfig:
        def __init__(self, engine="python"):
            self.engine = engine

    assert module.config(CandidateConfig, engine="rust").engine == "rust"


def test_hot_and_cold_key_classification_excludes_indexes():
    helper = module._helper
    assert helper.classify_redis_key(b"fixture:record:abc", "fixture") == "hot"
    assert (
        helper.classify_redis_key(b"fixture:record:abc:operation:def", "fixture") == "cold_receipt"
    )
    assert (
        helper.classify_redis_key(b"fixture:component:abc:def:operation:ghi", "fixture")
        == "cold_receipt"
    )
    assert helper.classify_redis_key(b"fixture:receipt:abc:def", "fixture") == "cold_receipt"
    assert helper.classify_redis_key(b"fixture:result:abc:def", "fixture") == "cold_result"
    assert helper.classify_redis_key(b"fixture:receipt-index:abc", "fixture") == "other"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,staged,expected",
    [(3, True, [(1, 2), (2, 3)]), (2, True, [(1, 2)]), (3, False, [(1, 3)])],
)
async def test_activation_respects_public_idle_stages_and_nav_direct(target, staged, expected):
    class Store:
        def __init__(self):
            self.calls = []

        async def initialize(self):
            pass

        async def activate_storage_format(self, **kwargs):
            if staged:
                assert kwargs["target"] == kwargs["expected"] + 1
            assert kwargs["old_workers_drained"] is True
            assert kwargs["dry_run"] is False
            assert kwargs["operation_id"] == f"benchmark-format-{kwargs['target']}"
            self.calls.append((kwargs["expected"], kwargs["target"]))

    store = Store()
    await module.activate_format(store, target, staged=staged)
    assert store.calls == expected
