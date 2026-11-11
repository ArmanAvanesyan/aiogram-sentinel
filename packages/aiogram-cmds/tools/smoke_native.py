"""Import the installed ABI3 wheel and exercise every advertised CPU capability."""

from importlib.metadata import version

import _aiogram_cmds_native as native

assert type(native.abi_version()) is int and native.abi_version() == 1
assert native.version() == version("aiogram-cmds-native")
assert native.resolve_profile(
    ["start", "help", "start"], ["help"], ["start", "help"]
) == ["start", "start"]
rows = [("start", "Սկսել")]
native.validate_commands(rows)
digest = native.fingerprint("123", '{"chat_id":42,"type":"chat"}', "null", rows)
snapshot = native.compile([("member", [("hy", rows)])])
assert snapshot.resolve_batch(
    [("member", "hy", "123", '{"chat_id":42,"type":"chat"}', "null")]
) == [digest]
