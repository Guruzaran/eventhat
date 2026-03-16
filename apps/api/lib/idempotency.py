import hashlib
import json
from typing import Any

from redis.asyncio import Redis


def make_key(verb: str, noun: str, args: dict[str, Any], caller_id: str, tx_id: int) -> str:
    """SHA-256 of verb + noun + sorted args + caller_id + tx_id, prefixed with 'idem:'"""
    payload = json.dumps(
        {
            "verb": verb,
            "noun": noun,
            "args": args,
            "caller_id": str(caller_id),
            "tx_id": tx_id,
        },
        sort_keys=True,
        default=str,  # handles UUID, SlotConfig, etc.
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"idem:{digest}"


async def check(key: str, redis: Redis) -> dict | None:
    """Return cached result dict or None if not found."""
    value = await redis.get(key)
    if value is None:
        return None
    return json.loads(value)


async def cache(key: str, result: dict[str, Any], redis: Redis) -> None:
    """Store result in Redis with 1-hour TTL."""
    await redis.set(key, json.dumps(result, default=str), ex=3600)