"""Application profiles and caller-owned menu confirmations; no FSM dependency."""

import argparse
import asyncio
import logging
import os

from aiogram import Bot
from aiogram.client.session.base import BaseSession

from aiogram_cmds import (
    CmdsConfig,
    CommandDef,
    CommandScopeManager,
    ProfileDef,
)


class DryRunSession(BaseSession):
    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        logging.getLogger(__name__).debug(
            "Dry-run Bot API method %s", type(method).__name__
        )
        return True

    async def stream_content(self, url, **kwargs):
        yield b""


async def main(dry_run: bool) -> None:
    token = "123456:DRY_RUN" if dry_run else os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN or use --dry-run")
    bot = Bot(token, session=DryRunSession() if dry_run else None)
    config = CmdsConfig(
        commands={"start": CommandDef(descriptions={"en": "Start the bot"})},
        profiles={"member": ProfileDef(include=["start"])},
    )
    manager = CommandScopeManager(bot, config=config)
    confirmed = None
    try:
        for _ in range(2):
            result = await manager.apply_profile(
                42,
                "member",
                language="en",
                language_code=None,
                previous_fingerprint=confirmed,
            )
            # A real application persists this with its own writer coordination.
            confirmed = result.confirmed_fingerprint
            print(result.status)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    asyncio.run(main(args.dry_run))
