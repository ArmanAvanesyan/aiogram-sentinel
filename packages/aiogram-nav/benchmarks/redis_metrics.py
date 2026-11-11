"""Wire-level RESP accounting for a dedicated benchmark Redis primary.

The stream proxy counts actual consumed bytes, not JSON-size estimates. Instrumented
connections run only in this benchmark, never inside the library or its users.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.connection import Connection


@dataclass
class WireMetrics:
    sent: int = 0
    received: int = 0
    responses: int = 0
    flushes: int = 0
    commands: Counter = field(default_factory=Counter)

    def reset(self):
        self.sent = self.received = self.responses = self.flushes = 0
        self.commands.clear()

    def snapshot(self):
        return dict(
            sent=self.sent,
            received=self.received,
            responses=self.responses,
            flushes=self.flushes,
            commands=dict(self.commands),
        )


class CountedReader:
    def __init__(self, reader, metrics):
        self.reader, self.metrics = reader, metrics

    async def read(self, *args, **kwargs):
        data = await self.reader.read(*args, **kwargs)
        self.metrics.received += len(data)
        return data

    async def readexactly(self, *args, **kwargs):
        data = await self.reader.readexactly(*args, **kwargs)
        self.metrics.received += len(data)
        return data

    async def readline(self, *args, **kwargs):
        data = await self.reader.readline(*args, **kwargs)
        self.metrics.received += len(data)
        return data

    async def readuntil(self, *args, **kwargs):
        data = await self.reader.readuntil(*args, **kwargs)
        self.metrics.received += len(data)
        return data

    def __getattr__(self, name):
        return getattr(self.reader, name)


def command_name(packed):
    # Library calls here send one RESP command per flush, without pipelining.
    first = packed[0]
    offset = first.index(b"\r\n") + 2
    offset = first.index(b"\r\n", offset) + 2
    end = first.index(b"\r\n", offset)
    return first[offset:end].decode("ascii").lower()


class CountedConnection(Connection):
    def __init__(self, *args, metrics, **kwargs):
        self.metrics = metrics
        super().__init__(*args, **kwargs)

    async def _connect(self):
        await super()._connect()
        self._reader = CountedReader(self._reader, self.metrics)

    async def send_packed_command(self, command, *args, **kwargs):
        packed = (
            [command.encode()]
            if isinstance(command, str)
            else [command]
            if isinstance(command, bytes)
            else command
        )
        self.metrics.sent += sum(len(chunk) for chunk in packed)
        self.metrics.flushes += 1
        self.metrics.commands[command_name(packed)] += 1
        return await super().send_packed_command(command, *args, **kwargs)

    async def read_response(self, *args, **kwargs):
        self.metrics.responses += 1
        return await super().read_response(*args, **kwargs)


def client(url):
    metrics = WireMetrics()
    pool = ConnectionPool.from_url(
        url,
        connection_class=CountedConnection,
        metrics=metrics,
        socket_timeout=5,
        socket_connect_timeout=5,
    )
    return Redis(connection_pool=pool), metrics
