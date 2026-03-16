import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
    )
    return _pool


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        await create_pool()
    return _pool
