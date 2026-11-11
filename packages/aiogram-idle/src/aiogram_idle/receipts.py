"""Tagged immutable effect results; JSON values cannot impersonate typed receipts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .errors import EffectUnknown
from .models import (
    ActionReceipt,
    ActivitySpec,
    IdleConversationKey,
    JsonValue,
    MessageRef,
    freeze_json,
    thaw_json,
)
from .presentation import DeliveryReceipt, PromptReceipt


def encode_result(value: object) -> JsonValue:
    if isinstance(value, ActionReceipt):
        spec = value.replacement
        return freeze_json(
            {
                "kind": "action",
                "value": {
                    "operation_id": value.operation_id,
                    "disposition": value.disposition,
                    "details": value.details,
                    "component_updates": value.component_updates,
                    "replacement": None
                    if spec is None
                    else {
                        "activity_key": spec.activity_key,
                        "policy_id": spec.policy_id,
                        "adapter_key": spec.adapter_key,
                        "params": spec.params,
                        "expires_at": spec.expires_at,
                    },
                },
            },
            max_bytes=8_388_608,
        )
    if isinstance(value, (PromptReceipt, DeliveryReceipt)):
        body: dict[str, object] = {
            "messages": [
                {"chat_id": ref.chat_id, "message_id": ref.message_id} for ref in value.messages
            ]
        }
        if isinstance(value, DeliveryReceipt):
            body["unavailable"] = value.unavailable
            return freeze_json({"kind": "delivery", "value": body})
        key = value.key
        body.update(
            prompt_id=value.prompt_id,
            shown_at=value.shown_at,
            controls=value.controls,
            locale=value.locale,
            continue_token=value.continue_token,
            cancel_token=value.cancel_token,
            key=None
            if key is None
            else {
                "namespace": key.namespace,
                "bot_id": key.bot_id,
                "chat_id": key.chat_id,
                "user_id": key.user_id,
                "tenant_id": key.tenant_id,
            },
        )
        return freeze_json({"kind": "prompt", "value": body})
    return freeze_json({"kind": "json", "value": value}, max_bytes=8_388_608)


def decode_result(value: JsonValue) -> object:
    if not isinstance(value, Mapping) or "kind" not in value or "value" not in value:
        raise EffectUnknown("Effect result schema is unsupported")
    body = value["value"]
    if value["kind"] == "json":
        return thaw_json(body)
    if not isinstance(body, Mapping):
        raise EffectUnknown("Typed effect receipt is invalid")
    if value["kind"] == "action":
        replacement = body.get("replacement")
        spec = None
        if isinstance(replacement, Mapping):
            spec = ActivitySpec(
                str(replacement["activity_key"]),
                str(replacement["policy_id"]),
                str(replacement["adapter_key"]),
                cast(Mapping[str, JsonValue], replacement["params"]),
                cast(float | None, replacement.get("expires_at")),
            )
        return ActionReceipt(
            str(body["operation_id"]),
            str(body["disposition"]),
            spec,
            cast(Mapping[str, JsonValue], body["details"]),
            cast(Mapping[str, JsonValue], body.get("component_updates", {})),
        )
    refs = cast(tuple[Mapping[str, JsonValue], ...], body["messages"])
    messages = tuple(
        MessageRef(cast(int, ref["chat_id"]), cast(int, ref["message_id"])) for ref in refs
    )
    if value["kind"] == "delivery":
        return DeliveryReceipt(messages, cast(bool, body["unavailable"]))
    if value["kind"] == "prompt":
        key_fields = body.get("key")
        key = None
        if isinstance(key_fields, Mapping):
            key = IdleConversationKey(
                str(key_fields["namespace"]),
                cast(int, key_fields["bot_id"]),
                cast(int, key_fields["chat_id"]),
                cast(int, key_fields["user_id"]),
                cast(str | None, key_fields.get("tenant_id")),
            )
        return PromptReceipt(
            str(body["prompt_id"]),
            messages,
            cast(float, body["shown_at"]),
            str(body["controls"]),
            str(body["locale"]),
            str(body["continue_token"]),
            str(body["cancel_token"]),
            key,
        )
    raise EffectUnknown("Unknown effect receipt kind")
