"""
Session Manager — conversation history + confirmation state in Redis/PostgreSQL.
"""
import json
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

import asyncpg
from redis.asyncio import Redis


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

async def get_or_create_session(user_id: UUID, pool: asyncpg.Pool) -> dict:
    """Return an active session < 2 hours old, or create a new one."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, messages, active_event_id, last_active_at
            FROM ai_sessions
            WHERE user_id = $1
              AND last_active_at > NOW() - INTERVAL '2 hours'
            ORDER BY last_active_at DESC
            LIMIT 1
            """,
            user_id,
        )
        if row:
            # Bump last_active_at
            await conn.execute(
                "UPDATE ai_sessions SET last_active_at = NOW() WHERE id = $1",
                row["id"],
            )
            return dict(row)

        # Create new session
        new_row = await conn.fetchrow(
            """
            INSERT INTO ai_sessions (user_id, messages)
            VALUES ($1, '[]'::jsonb)
            RETURNING id, user_id, messages, active_event_id, last_active_at
            """,
            user_id,
        )
        return dict(new_row)


async def add_message(
    session_id: UUID,
    role: str,          # "user" | "assistant"
    content: str,
    pool: asyncpg.Pool,
) -> None:
    """Append one message to ai_sessions.messages JSONB array."""
    message = {"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()}
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE ai_sessions
            SET messages = messages || $1::jsonb,
                last_active_at = NOW()
            WHERE id = $2
            """,
            json.dumps([message]),
            session_id,
        )


async def get_messages(session_id: UUID, pool: asyncpg.Pool) -> list[dict]:
    """Return the last 20 messages for the session."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT messages FROM ai_sessions WHERE id = $1",
            session_id,
        )
        if not row:
            return []
        messages = json.loads(row["messages"]) if isinstance(row["messages"], str) else row["messages"]
        return messages[-20:]  # keep last 20


# ---------------------------------------------------------------------------
# Transaction ID (increments per message, used for idempotency keys)
# ---------------------------------------------------------------------------

async def increment_tx_id(session_id: UUID, redis: Redis) -> int:
    """Atomically increment and return the tx counter for this session."""
    key = f"tx_id:{session_id}"
    tx_id = await redis.incr(key)
    await redis.expire(key, 7200)  # 2 hour TTL matches session lifetime
    return tx_id


# ---------------------------------------------------------------------------
# Confirmation state (WRITE / DESTRUCTIVE commands pending user confirm)
# ---------------------------------------------------------------------------

async def store_confirmation(
    session_id: UUID,
    parsed_command: dict,   # ParsedCommand serialized to dict
    redis: Redis,
) -> str:
    """
    Serialize parsed_command into Redis with a UUID token.
    Client receives the token only — cannot modify what executes.
    TTL: 600 seconds (10 minutes).
    """
    token = str(uuid4())
    payload = json.dumps(
        {"session_id": str(session_id), "parsed_command": parsed_command},
        default=str,
    )
    await redis.set(f"confirm:{token}", payload, ex=600)
    return token


async def consume_confirmation(token: str, redis: Redis) -> dict | None:
    """
    Atomic GET + DELETE of confirmation state.
    Returns the stored dict or None if expired / never existed.
    GETDEL prevents double-execution on double-click or network retry.
    """
    value = await redis.getdel(f"confirm:{token}")
    if value is None:
        return None
    return json.loads(value)
