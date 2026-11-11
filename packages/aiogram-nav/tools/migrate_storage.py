"""Assess or deliberately activate a drained navigation Redis namespace."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict

from aiogram_nav.errors import NavigationError
from aiogram_nav.storage.redis import RedisNavigationRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("AIOGRAM_NAV_REDIS_URL"),
        help="Prefer AIOGRAM_NAV_REDIS_URL to keep credentials out of shell history",
    )
    parser.add_argument("--prefix", default="aiogram-nav")
    parser.add_argument("--operation-id")
    parser.add_argument("--expected", type=int, choices=(1, 2), default=1)
    parser.add_argument("--target", type=int, choices=(2, 3), default=2)
    parser.add_argument(
        "--migrate-all",
        action="store_true",
        help="Explicitly convert bounded pages after format 3 activation",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--cursor", default="0:0")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Activate the selected format; default is a read-only assessment",
    )
    parser.add_argument(
        "--old-workers-drained",
        action="store_true",
        help="Explicit operator assertion that all old writers have drained",
    )
    args = parser.parse_args()
    if not args.redis_url:
        parser.error("Set AIOGRAM_NAV_REDIS_URL or supply --redis-url")
    if args.apply and (not args.operation_id or not args.old_workers_drained):
        parser.error("--apply requires --operation-id and --old-workers-drained")
    if not 1 <= args.batch_size <= 1000 or not 1 <= args.max_pages <= 10000:
        parser.error("--batch-size and --max-pages must be bounded positive integers")
    return args


async def main(args: argparse.Namespace) -> None:
    from redis.asyncio import Redis

    client = Redis.from_url(args.redis_url, socket_timeout=5, socket_connect_timeout=5)
    repository = RedisNavigationRepository(redis=client, prefix=args.prefix)
    try:
        report = await repository.activate_storage_format(
            operation_id=args.operation_id or "read-only-assessment",
            expected=args.expected,
            target=args.target,
            dry_run=not args.apply,
            old_workers_drained=args.old_workers_drained,
        )
        print(json.dumps(asdict(report), sort_keys=True))
        if args.migrate_all:
            cursor = args.cursor
            for _ in range(args.max_pages):
                page = await repository.migrate_storage_page(cursor=cursor, limit=args.batch_size)
                print(json.dumps(page, sort_keys=True))
                if page["cursor"] is None:
                    break
                cursor = str(page["cursor"])
    finally:
        await repository.close()
        await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main(arguments()))
    except NavigationError as error:
        raise SystemExit(str(error)) from None
    except ImportError:
        raise SystemExit("Install aiogram-nav[redis] to assess Redis storage") from None
    except (ValueError, TypeError):
        raise SystemExit("Redis URL or storage configuration is invalid") from None
