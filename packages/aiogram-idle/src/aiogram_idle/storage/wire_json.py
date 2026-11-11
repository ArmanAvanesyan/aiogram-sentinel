"""Strict plain JSON for bounded generic storage wire headers."""

from __future__ import annotations

import json
from typing import cast

from ..errors import BackendInconsistent


def compact(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict(raw: str) -> dict[str, object]:
    def unique(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in values:
            if key in result:
                raise BackendInconsistent("Repeated cold storage field")
            result[key] = item
        return result

    try:
        result: object = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError, RecursionError) as error:
        raise BackendInconsistent("Malformed cold storage state") from error
    if not isinstance(result, dict):
        raise BackendInconsistent("Invalid cold storage state")
    stack: list[tuple[object, int]] = [(result, 0)]
    try:
        while stack:
            item, depth = stack.pop()
            if depth > 64:
                raise BackendInconsistent("Cold storage JSON nesting exceeds its bound")
            if isinstance(item, str):
                item.encode("utf-8")
            elif isinstance(item, dict):
                for key, value in cast(dict[str, object], item).items():
                    key.encode("utf-8")
                    stack.append((value, depth + 1))
            elif isinstance(item, list):
                stack.extend((value, depth + 1) for value in cast(list[object], item))
    except UnicodeError as error:
        raise BackendInconsistent(
            "Cold storage JSON must contain valid UTF-8 Unicode scalars"
        ) from error
    return cast(dict[str, object], result)
