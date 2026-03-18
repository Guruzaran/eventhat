"""
API Routes — POST /login, GET /me, POST /chat, POST /confirm, GET /audit
"""
import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent import compiler, formatter, gate, session as session_manager
from agent.executor import dispatch, DomainError
from agent.parser import parse
from db.pool import get_pool
from db.redis import get_redis
from models.commands import ConfirmationTier, ParsedCommand

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str

class ChatRequest(BaseModel):
    message: str

class ConfirmRequest(BaseModel):
    token: str
    action: str = "confirm"   # "confirm" | "cancel"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_current_user(request: Request, pool: asyncpg.Pool) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.email, u.display_name, u.role, u.org_id,
                   o.name AS org_name, o.slug AS org_slug
            FROM users u
            JOIN organizations o ON o.id = u.org_id
            WHERE u.id = $1
            """,
            UUID(user_id),
        )
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)


def _confirmation_card(cmd: ParsedCommand) -> dict:
    """Build human-readable confirmation card data."""
    tier = gate.classify(cmd)

    # Human-readable labels for each flag
    label_map = {
        "title": "Event name",
        "date": "Date",
        "slots": "Slots",
        "location": "Location",
        "price": "Price",
        "privacy": "Privacy",
        "status": "New status",
        "description": "Description",
        "event_id": "Event ID",
        "slot": "Slot",
        "signup_id": "Signup ID",
        "type": "Type",
        "message": "Message",
    }

    details = []
    for flag, value in cmd.args.items():
        label = label_map.get(flag, flag.replace("_", " ").title())
        if flag == "slots" and hasattr(value, "count"):
            value = f"{value.count} shift(s) × {value.capacity} people"
        elif flag == "price":
            value = f"${value / 100:.2f}"
        details.append({"label": label, "value": str(value)})

    action_titles = {
        "event:create": "Create Event",
        "event:update": "Update Event",
        "event:clone": "Clone Event",
        "signup:confirm": "Confirm Signup",
        "signup:cancel": "Cancel Signup",
        "payment:refund": "Issue Refund",
        "notify:send": "Send Notification",
    }

    return {
        "title": action_titles.get(cmd.key, cmd.key.replace(":", " ").title()),
        "command": cmd.key,
        "details": details,
        "warning": "This action is hard to undo." if tier == ConfirmationTier.DESTRUCTIVE else None,
        "tier": tier.value,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(body: LoginRequest, request: Request, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.email, u.display_name, u.role, u.org_id,
                   o.name AS org_name
            FROM users u
            JOIN organizations o ON o.id = u.org_id
            WHERE u.email = $1
            """,
            body.email,
        )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    request.session["user_id"] = str(row["id"])
    return {
        "ok": True,
        "user": {
            "id": str(row["id"]),
            "email": row["email"],
            "display_name": row["display_name"],
            "role": row["role"],
            "org_name": row["org_name"],
        },
    }


@router.get("/me")
async def me(request: Request, pool: asyncpg.Pool = Depends(get_pool)):
    user = await _get_current_user(request, pool)
    return {"user": {k: str(v) if isinstance(v, UUID) else v for k, v in user.items()}}


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Chat — the full 6-layer pipeline
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    redis = await get_redis()
    user = await _get_current_user(request, pool)
    user_id = user["id"]
    org_id  = user["org_id"]

    # 1. Get or create session
    sess = await session_manager.get_or_create_session(user_id, pool)
    session_id = sess["id"]

    # 2. Load conversation history
    history = await session_manager.get_messages(session_id, pool)

    # 3. Store user message
    await session_manager.add_message(session_id, "user", body.message, pool)

    # 4. Build caller context for the compiler
    caller_ctx = {
        "role": user["role"],
        "org_id": org_id,
        "org_name": user["org_name"],
        "active_event_id": str(sess.get("active_event_id") or "UNKNOWN"),
    }

    # 5. Compile natural language → CLI string  (LAYER 2)
    raw_cli = await compiler.compile(body.message, history, caller_ctx, pool, redis)

    # 6. Parse CLI string → typed command  (LAYER 3)
    parsed = parse(raw_cli, role=user["role"])

    # 7. Parse error → return immediately, no retry
    if hasattr(parsed, "error_code"):
        error_msg = parsed.message
        await session_manager.add_message(session_id, "assistant", error_msg, pool)
        return {
            "type": "parse_error",
            "message": error_msg,
            "cli": raw_cli,
            "is_clarification": parsed.is_clarification,
        }

    # 8. Classify confirmation tier  (LAYER 4)
    tier = gate.classify(parsed)

    # 9. WRITE / DESTRUCTIVE → store in Redis, return confirmation card
    if tier in (ConfirmationTier.WRITE, ConfirmationTier.DESTRUCTIVE):
        token = await session_manager.store_confirmation(
            session_id, parsed.model_dump(), redis
        )
        card = _confirmation_card(parsed)
        return {
            "type": "confirmation_required",
            "token": token,
            "card": card,
            "cli": raw_cli,
        }

    # 10. READ → execute immediately  (LAYER 5)
    tx_id = await session_manager.increment_tx_id(session_id, redis)
    try:
        result = await dispatch(parsed, user_id, org_id, session_id, tx_id, pool, redis)
    except DomainError as e:
        return {"type": "error", "message": e.message, "code": e.code, "cli": raw_cli}

    response_text = formatter.format_response(parsed, result)
    await session_manager.add_message(session_id, "assistant", response_text, pool)

    return {
        "type": "success",
        "message": response_text,
        "cli": raw_cli,
        "replayed": result.replayed,
    }


# ---------------------------------------------------------------------------
# Confirm — execute a stored WRITE/DESTRUCTIVE command
# ---------------------------------------------------------------------------

@router.post("/confirm")
async def confirm(
    body: ConfirmRequest,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    redis = await get_redis()
    user = await _get_current_user(request, pool)

    # Atomic get + delete — prevents double-execution
    stored = await session_manager.consume_confirmation(body.token, redis)
    if stored is None:
        raise HTTPException(
            status_code=410,
            detail="Confirmation expired or already used. Please re-issue the command.",
        )

    if body.action == "cancel":
        return {"type": "cancelled", "message": "Action cancelled."}

    # Reconstruct ParsedCommand from stored dict
    cmd_data = stored["parsed_command"]
    # Re-parse from raw_cli — avoids SlotConfig deserialization issues
    from agent.parser import parse as reparse
    parsed = reparse(cmd_data["raw_cli"], role=user["role"])
    if hasattr(parsed, "error_code"):
        return {"type": "error", "message": f"Could not replay command: {parsed.message}"}
    session_id = UUID(stored["session_id"])

    tx_id = await session_manager.increment_tx_id(session_id, redis)
    try:
        result = await dispatch(
            parsed,
            user["id"],
            user["org_id"],
            session_id,
            tx_id,
            pool,
            redis,
        )
    except DomainError as e:
        return {"type": "error", "message": e.message, "code": e.code}

    response_text = formatter.format_response(parsed, result)
    await session_manager.add_message(session_id, "assistant", response_text, pool)

    return {
        "type": "success",
        "message": response_text,
        "replayed": result.replayed,
    }


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit")
async def audit(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    user = await _get_current_user(request, pool)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, raw_cli, parsed_verb, parsed_noun,
                   result_status, error_code, created_at
            FROM audit_log
            WHERE caller_id = $1
            ORDER BY created_at DESC
            LIMIT 50
            """,
            user["id"],
        )
    return {
        "audit": [
            {**dict(r), "id": str(r["id"]), "created_at": r["created_at"].isoformat()}
            for r in rows
        ]
    }
