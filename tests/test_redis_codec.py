"""Persistence format rejects corruption rather than manufacturing trusted records."""

import json
from dataclasses import replace

import pytest

from aiogram_idle.errors import BackendInconsistent, SchemaUnsupported
from aiogram_idle.models import (
    ActionReceipt,
    ActivitySnapshot,
    ActivitySpec,
    ConfigManifest,
    IdleConversationKey,
    IdleSnapshot,
    MessageRef,
    PendingOperation,
    Phase,
    RuntimeSnapshot,
    SessionSnapshot,
)
from aiogram_idle.policies import ExemptPolicy, PromptPolicy, QuietRestorePolicy
from aiogram_idle.presentation import DeliveryReceipt, PromptReceipt
from aiogram_idle.storage.codec import decode, decode_value, encode, loads_snapshot
from aiogram_idle.storage.state import Claim, ControlToken, Job, OperationReceipt


def snapshot():
    key = IdleConversationKey("test", 1, 2, 2)
    activity = ActivitySnapshot(
        "session",
        "activity",
        "draft",
        1,
        "prompt",
        "flow",
        {"nested": [1, True, None, {"language": "hy"}]},
        10,
        20,
        500,
    )
    prompt = PromptReceipt("prompt", (MessageRef(2, 3),), 30, "hybrid", "hy", "yes", "no", key)
    receipt = ActionReceipt(
        "resume", "replacement", ActivitySpec("next", "prompt", "flow"), {"confirmed": True}
    )
    operation = PendingOperation(
        "resume",
        "continue",
        "adapter_done",
        31,
        2,
        {"effect": {"kind": "action", "value": [1, 2]}},
        receipt,
        "unknown response",
    )
    return RuntimeSnapshot(
        key,
        SessionSnapshot("session", 500),
        activity,
        IdleSnapshot(Phase.RESUMING, 40, prompt, operation, 2, 45),
        8,
        900,
        {"component": {"current": "settings"}},
    )


def test_full_runtime_roundtrip():
    original = snapshot()
    restored = loads_snapshot(encode(original))
    assert restored == original
    assert restored is not original
    with pytest.raises(TypeError):
        restored.activity.params["new"] = 2


@pytest.mark.parametrize(
    "value",
    [
        ExemptPolicy(),
        PromptPolicy(2, 3, "reply"),
        QuietRestorePolicy(4),
        ConfigManifest("generation", True, "digest"),
        Job(3, 100, 101, "owner", 200),
        DeliveryReceipt((MessageRef(2, 3),), True),
        Claim(IdleConversationKey("test", 1, 2, 2), "owner", 1, 30, 20),
    ],
)
def test_contract_roundtrip(value):
    assert decode(encode(value)) == value


def test_backend_envelope_roundtrip():
    runtime = snapshot()
    token = ControlToken(runtime.key, "token", "prompt", "session", "activity", 400)
    envelope = {
        "snapshot": runtime,
        "policy": PromptPolicy(),
        "receipts": {
            "open": OperationReceipt("fingerprint", runtime.session, 900),
            "enter": OperationReceipt("other", runtime.activity, 900),
            "runtime": OperationReceipt("third", runtime, 900),
            "clear": OperationReceipt("fourth", True, 900),
        },
        "tokens": {"token": token},
        "json": {"type": "SessionSnapshot", "value": {"session_id": "spoof"}},
        "list": [1, 2],
        "tuple": (3, 4),
    }
    assert decode(encode(envelope)) == envelope


@pytest.mark.parametrize("value", [float("inf"), float("nan"), object(), {1: "bad"}])
def test_reject_non_json(value):
    with pytest.raises(BackendInconsistent):
        encode(value)


@pytest.mark.parametrize(
    "body",
    [
        "{",
        "[]",
        '{"schema_version":1,"schema_version":1,"value":null}',
        '{"schema_version":1,"value":NaN}',
        '{"schema_version":1,"value":{"type":"list","value":{}}}',
    ],
)
def test_malformed_json(body):
    with pytest.raises(BackendInconsistent):
        decode(body)


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_schema_versions(version):
    with pytest.raises(SchemaUnsupported):
        decode(json.dumps({"schema_version": version, "value": None}))


def test_unknown_tag():
    with pytest.raises(SchemaUnsupported):
        decode_value({"type": "UnregisteredClass", "value": {}})


@pytest.mark.parametrize(
    "field,value", [("store_version", True), ("store_version", 0), ("recovery_until", "tomorrow")]
)
def test_malformed_record(field, value):
    raw = json.loads(encode(snapshot()))
    raw["value"]["value"][field] = value
    with pytest.raises(BackendInconsistent):
        decode(json.dumps(raw))


def test_missing_and_extra_fields():
    raw = json.loads(encode(SessionSnapshot("session", 500)))
    raw["value"]["value"]["extra"] = 1
    with pytest.raises(BackendInconsistent):
        decode(json.dumps(raw))
    del raw["value"]["value"]["extra"]
    del raw["value"]["value"]["revision"]
    with pytest.raises(BackendInconsistent):
        decode(json.dumps(raw))


def test_cross_session_corruption():
    with pytest.raises(BackendInconsistent):
        encode(replace(snapshot(), session=SessionSnapshot("different", 500)))


def test_invalid_private_identity():
    raw = json.loads(encode(IdleConversationKey("test", 1, 2, 2)))
    raw["value"]["value"]["user_id"] = 3
    with pytest.raises(BackendInconsistent):
        decode(json.dumps(raw))


def test_depth_limit():
    value = None
    for _ in range(66):
        value = [value]
    with pytest.raises(BackendInconsistent):
        encode(value)


def test_snapshot_loader_rejects_other_root():
    with pytest.raises(BackendInconsistent):
        loads_snapshot(encode(True))


def test_config_update_receipt_roundtrip():
    value = OperationReceipt(
        "config-fingerprint", ConfigManifest("generation", False, "digest"), 500
    )
    assert decode(encode(value)) == value


@pytest.mark.parametrize(
    "value",
    [
        PendingOperation("", "continue"),
        PendingOperation("operation", "continue", attempts=-1),
        PromptReceipt("prompt", controls="unknown"),
        MessageRef(2, 0),
        Job(0, 10, 10),
        ConfigManifest("generation", 1, "digest"),
    ],
)
def test_invalid_unvalidated_dataclass_fields(value):
    with pytest.raises(BackendInconsistent):
        encode(value)


def test_tagged_contract_cannot_infiltrate_application_json():
    raw = json.loads(encode(snapshot()))
    raw["value"]["value"]["components"] = json.loads(encode(SessionSnapshot("nested", 500)))[
        "value"
    ]
    with pytest.raises(BackendInconsistent):
        decode(json.dumps(raw))


def test_invalid_policy_numeric_types():
    raw = json.loads(encode(PromptPolicy()))
    raw["value"]["value"]["after_seconds"] = True
    with pytest.raises(BackendInconsistent):
        decode(json.dumps(raw))


def test_json_size_bound():
    value = PendingOperation("operation", "continue", effects={"text": "x" * 16000})
    # Existing model validates JSON byte limits; encoding preserves that protection.
    assert decode(encode(value)) == value
    raw = json.loads(encode(value))
    raw["value"]["value"]["effects"]["value"]["text"] = "x" * 8_388_608
    with pytest.raises(BackendInconsistent):
        decode(json.dumps(raw))


def test_unknown_operation_semantics_are_not_interpreted_as_cleanup():
    with pytest.raises(SchemaUnsupported):
        encode(PendingOperation("future-operation", "future-kind"))
