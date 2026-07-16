import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: AsyncIOMotorClient | None = None
_timescale_pool: asyncpg.Pool | None = None


def get_database() -> AsyncIOMotorDatabase:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client.get_default_database()


async def get_timescale_pool() -> asyncpg.Pool:
    global _timescale_pool
    if _timescale_pool is None:
        # asyncpg's own default (min_size=10, max_size=10) is sized for a
        # dedicated database -- too large once TimescaleDB is shared with
        # another app on a connection-constrained instance (see the
        # production deployment plan). This process only ever acquires one
        # connection at a time (see telemetry/repository.py), so a small
        # pool is plenty.
        _timescale_pool = await asyncpg.create_pool(
            settings.timescale_uri, min_size=2, max_size=5
        )
    return _timescale_pool
