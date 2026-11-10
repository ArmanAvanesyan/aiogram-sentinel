"""Assess or explicitly activate/migrate a drained development/production namespace."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from aiogram_idle.errors import IdleError
from aiogram_idle.storage.deployment import RedisDeploymentAttestation
from aiogram_idle.storage.redis import RedisIdleBackend


async def run(args: argparse.Namespace) -> None:
    url = os.environ.get("AIOGRAM_IDLE_REDIS_URL")
    if not url:
        raise ValueError("Set AIOGRAM_IDLE_REDIS_URL; credentials are never CLI arguments")
    deployment = None
    if args.attestation_file:
        deployment = RedisDeploymentAttestation(
            **json.loads(await asyncio.to_thread(Path(args.attestation_file).read_text))
        )
    backend = RedisIdleBackend.from_url(url, prefix=args.prefix, deployment=deployment)
    try:
        await backend.initialize()
        if args.migrate:
            result = await backend.migrate_storage_records(
                cursor=args.cursor, limit=args.limit, dry_run=not args.apply
            )
        else:
            result = await backend.activate_storage_format(
                operation_id=args.operation_id,
                old_workers_drained=args.old_workers_drained,
                dry_run=not args.apply,
            )
        print(json.dumps(asdict(result), sort_keys=True))
    finally:
        await backend.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--operation-id", default="storage-format-2")
    parser.add_argument(
        "--apply", action="store_true", help="Apply instead of read-only assessment"
    )
    parser.add_argument("--old-workers-drained", action="store_true")
    parser.add_argument("--migrate", action="store_true", help="Migrate one bounded record page")
    parser.add_argument("--cursor", default="0")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--attestation-file", type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (IdleError, ValueError, TypeError, OSError) as error:
        parser.exit(2, f"Storage administration failed: {error}\n")


if __name__ == "__main__":
    main()
