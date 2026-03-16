import redis.asyncio as aioredis
import os
from dotenv import load_dotenv

load_dotenv()

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            os.environ["REDIS_URL"],
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis
