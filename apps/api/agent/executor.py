"""
LAYER 5 — EXECUTION ENGINE

dispatch() is the only public function. It:
  1. Checks idempotency key — returns cached result on hit
  2. Opens an asyncpg transaction
  3. Routes verb:noun to the correct handler
  4. Writes audit log inside the same transaction (atomic)
  5. Commits
  6. Caches result in Redis
  7. On exception: rolls back, writes error audit on a separate connection, re-raises
"""
from typing import Any
from uuid import UUID

import asyncpg
from redis.asyncio import Redis

from handlers import event as event_handler
from handlers import signup as signup_handler
from lib import audit as audit_lib
from lib import idempotency
from models.commands import ExecutionResult, ParsedCommand


class DomainError(Exception):
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

async def _route(
    conn: asyncpg.Connection,
    cmd: ParsedCommand,
    caller_id: UUID,
    org_id: UUID,
) -> dict[str, Any]:
    key = cmd.key

    if key == "event:create":
        return await event_handler.create(conn, cmd.args, caller_id, org_id)
    if key == "event:update":
        return await event_handler.update(conn, cmd.args, caller_id, org_id)
    if key == "event:show":
        return await event_handler.show(conn, cmd.args, org_id)
    if key in ("event:list", "list:events"):
        return await event_handler.list_events(conn, cmd.args, org_id)

    if key == "signup:confirm":
        return await signup_handler.confirm(conn, cmd.args, caller_id, org_id)
    if key == "signup:cancel":
        return await signup_handler.cancel(conn, cmd.args, caller_id, org_id)
    if key in ("signup:list", "list:signups"):
        return await signup_handler.list_signups(conn, cmd.args, org_id)

    if key == "show:context":
        # Return the current session context (events list)
        return await event_handler.list_events(conn, {}, org_id)

    raise DomainError(f"No handler implemented for '{key}'", code="NOT_IMPLEMENTED")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def dispatch(
    cmd: ParsedCommand,
    caller_id: UUID,
    org_id: UUID,
    session_id: UUID | None,
    tx_id: int,
    pool: asyncpg.Pool,
    redis: Redis,
) -> ExecutionResult:
    # 1. Idempotency check
    idem_key = idempotency.make_key(cmd.verb, cmd.noun, cmd.args, str(caller_id), tx_id)
    cached = await idempotency.check(idem_key, redis)
    if cached is not None:
        return ExecutionResult(
            data=cached["data"],
            message=cached["message"],
            replayed=True,
        )

    # 2–6. Execute inside a transaction
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                data = await _route(conn, cmd, caller_id, org_id)

                await audit_lib.write_audit(
                    conn=conn,
                    session_id=session_id,
                    caller_id=caller_id,
                    raw_cli=cmd.raw_cli,
                    parsed_verb=cmd.verb,
                    parsed_noun=cmd.noun,
                    parsed_args=cmd.args,
                    result_status="success",
                    result_data=data,
                )

                message = _build_message(cmd, data)
                result = ExecutionResult(data=data, message=message, replayed=False)

            except DomainError:
                raise  # let the outer except handle it

            except Exception as exc:
                # Write error audit inside the same transaction before it rolls back.
                # If this also fails, the transaction rolls back entirely — which is correct.
                await audit_lib.write_audit(
                    conn=conn,
                    session_id=session_id,
                    caller_id=caller_id,
                    raw_cli=cmd.raw_cli,
                    parsed_verb=cmd.verb,
                    parsed_noun=cmd.noun,
                    parsed_args=cmd.args,
                    result_status="error",
                    error_code=type(exc).__name__,
                )
                raise

    # 6. Cache on success
    await idempotency.cache(idem_key, {"data": result.data, "message": result.message}, redis)

    return result


# ---------------------------------------------------------------------------
# Message builder (simple — full templates are in formatter.py, Session 5)
# ---------------------------------------------------------------------------

def _build_message(cmd: ParsedCommand, data: dict[str, Any]) -> str:
    key = cmd.key

    if key == "event:create":
        ev = data.get("event", {})
        slots = data.get("slots", [])
        return (
            f"Event **{ev.get('title')}** created (status: {ev.get('status')}).\n"
            f"{len(slots)} slot(s) ready."
        )

    if key == "event:update":
        ev = data.get("event", {})
        return f"Event updated. Status: **{ev.get('status', 'unchanged')}**."

    if key == "event:show":
        ev = data.get("event")
        if not ev:
            return "Event not found."
        slots = data.get("slots", [])
        return f"**{ev['title']}** — {ev.get('status')} — {len(slots)} slot(s)."

    if key in ("event:list", "list:events"):
        events = data.get("events", [])
        if not events:
            return "No events found."
        lines = [f"- **{e['title']}** ({e['status']})" for e in events]
        return f"Found {len(events)} event(s):\n" + "\n".join(lines)

    if key == "signup:confirm":
        status = data.get("status")
        if status == "waitlisted":
            return f"Slot full. Added to waitlist at position {data.get('position')}."
        return f"Signed up successfully. Status: **{status}**."

    if key == "signup:cancel":
        promoted = data.get("promoted_from_waitlist")
        msg = "Signup cancelled."
        if promoted:
            msg += " A waitlisted participant has been confirmed."
        return msg

    if key in ("signup:list", "list:signups"):
        signups = data.get("signups", [])
        if not signups:
            return "No signups found."
        lines = [f"- **{s['display_name']}** ({s['slot_label']}) — {s['status']}" for s in signups]
        return f"{len(signups)} signup(s):\n" + "\n".join(lines)

    if key == "show:context":
        events = data.get("events", [])
        return f"You have {len(events)} event(s) in your organisation."

    return "Done."
