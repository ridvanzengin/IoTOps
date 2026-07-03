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
        _timescale_pool = await asyncpg.create_pool(settings.timescale_uri)
    return _timescale_pool
