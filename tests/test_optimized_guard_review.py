"""Ownership/input guards remain active when Python strips assertions."""

import subprocess
import sys
import textwrap


def test_optimized_python_keeps_explicit_owned_state_guards():
    program = textwrap.dedent(
        """
        import asyncio
        from importlib.util import find_spec
        from aiogram_idle import IdleConversationKey, MemoryIdleBackend
        from aiogram_idle import engines
        from aiogram_idle.errors import ActivityConflict, ConfigurationError, OwnershipLost
        from aiogram_idle.models import ActivityGuard, RuntimeSnapshot, SessionSnapshot

        key = IdleConversationKey("optimized", 1, 42, 42)
        backend = MemoryIdleBackend(storage_format=3)
        record = RuntimeSnapshot(key, SessionSnapshot("session", backend.clock.now() + 60))
        engines.activity_guard = lambda *args, **kwargs: None
        try:
            backend._guard(record, ActivityGuard("session", "activity", 1))
        except ActivityConflict:
            pass
        else:
            raise RuntimeError("Absent activity escaped its typed ownership guard")

        async def check():
            try:
                await backend.canonical_component_transaction(
                    key, component="absent", expected_version=None,
                    record=record, ledger_delta={},
                )
            except ConfigurationError:
                pass
            else:
                raise RuntimeError("Missing canonical identity escaped its typed input guard")
            if find_spec("aiogram_nav") is not None:
                from aiogram_idle.integrations.nav.canonical_effects import CanonicalNavigationEffects
                class Outer:
                    async def record(self):
                        return record
                recorder = object.__new__(CanonicalNavigationEffects)
                recorder.outer = Outer()
                try:
                    await recorder.record()
                except OwnershipLost:
                    pass
                else:
                    raise RuntimeError("Absent idle operation escaped its ownership guard")
        asyncio.run(check())
        """
    )
    subprocess.run([sys.executable, "-O", "-c", program], check=True, timeout=30)
