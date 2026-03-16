"""
Event handlers — all run inside an asyncpg transaction passed from the executor.
Never open new connections or start new transactions here.
"""
from typing import Any
from uuid import UUID

import asyncpg


async def create(
    conn: asyncpg.Connection,
    args: dict[str, Any],
    caller_id: UUID,
    org_id: UUID,
) -> dict[str, Any]:
    slot_config = args.get("slots")  # SlotConfig(count, capacity)
    price_cents = args.get("price", 0)
    event_type = "paid_ticket" if price_cents and price_cents > 0 else args.get("type", "volunteer")

    # Insert event
    event_row = await conn.fetchrow(
        """
        INSERT INTO events (org_id, created_by, title, description, event_type,
                            status, starts_at, location, privacy)
        VALUES ($1, $2, $3, $4, $5, 'draft', $6::timestamptz, $7, $8)
        RETURNING id, title, status, starts_at, location, privacy, event_type, created_at
        """,
        org_id,
        caller_id,
        args["title"],
        args.get("description"),
        event_type,
        args.get("date"),        # ISO-8601 string, Postgres casts it
        args.get("location"),
        args.get("privacy", "public"),
    )

    event_id = event_row["id"]
    slots = []

    # Insert slots
    if slot_config:
        for i in range(slot_config.count):
            label = f"Shift {i + 1}" if slot_config.count > 1 else "General"
            slot_row = await conn.fetchrow(
                """
                INSERT INTO slots (event_id, label, capacity, price_cents)
                VALUES ($1, $2, $3, $4)
                RETURNING id, label, capacity, filled, price_cents
                """,
                event_id,
                label,
                slot_config.capacity,
                price_cents or 0,
            )
            slots.append(dict(slot_row))

    return {
        "event": dict(event_row),
        "slots": slots,
    }


async def update(
    conn: asyncpg.Connection,
    args: dict[str, Any],
    caller_id: UUID,
    org_id: UUID,
) -> dict[str, Any]:
    event_id = args["event_id"]

    # Build SET clause dynamically from provided args
    updatable = {
        "title": args.get("title"),
        "description": args.get("description"),
        "starts_at": args.get("date"),
        "location": args.get("location"),
        "privacy": args.get("privacy"),
        "status": args.get("status"),
    }
    fields = {k: v for k, v in updatable.items() if v is not None}

    if not fields:
        # Nothing to update — just return the current state
        row = await conn.fetchrow(
            "SELECT id, title, status, starts_at, location, privacy, event_type, updated_at FROM events WHERE id=$1 AND org_id=$2",
            event_id, org_id,
        )
        return {"event": dict(row) if row else {}}

    set_parts = []
    values = []
    for idx, (col, val) in enumerate(fields.items(), start=1):
        set_parts.append(f"{col} = ${idx}")
        values.append(val)

    values.extend([event_id, org_id])
    n = len(values)

    row = await conn.fetchrow(
        f"""
        UPDATE events
        SET {', '.join(set_parts)}, updated_at = NOW()
        WHERE id = ${n - 1} AND org_id = ${n}
        RETURNING id, title, status, starts_at, location, privacy, event_type, updated_at
        """,
        *values,
    )

    return {"event": dict(row) if row else {}}


async def show(
    conn: asyncpg.Connection,
    args: dict[str, Any],
    org_id: UUID,
) -> dict[str, Any]:
    event_id = args["event_id"]

    event_row = await conn.fetchrow(
        """
        SELECT id, title, description, event_type, status, starts_at,
               location, privacy, created_at, updated_at
        FROM events WHERE id=$1 AND org_id=$2
        """,
        event_id, org_id,
    )
    if not event_row:
        return {"event": None, "slots": []}

    slot_rows = await conn.fetch(
        "SELECT id, label, capacity, filled, price_cents FROM slots WHERE event_id=$1 ORDER BY created_at",
        event_id,
    )

    return {
        "event": dict(event_row),
        "slots": [dict(r) for r in slot_rows],
    }


async def list_events(
    conn: asyncpg.Connection,
    args: dict[str, Any],
    org_id: UUID,
) -> dict[str, Any]:
    status_filter = args.get("status")
    privacy_filter = args.get("privacy")

    conditions = ["org_id = $1"]
    values: list[Any] = [org_id]

    if status_filter and status_filter != "all":
        values.append(status_filter)
        conditions.append(f"status = ${len(values)}")

    if privacy_filter:
        values.append(privacy_filter)
        conditions.append(f"privacy = ${len(values)}")

    where = " AND ".join(conditions)
    rows = await conn.fetch(
        f"""
        SELECT id, title, status, starts_at, location, privacy, event_type, created_at
        FROM events WHERE {where} ORDER BY starts_at ASC NULLS LAST
        """,
        *values,
    )

    return {"events": [dict(r) for r in rows]}