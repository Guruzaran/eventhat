"""
Signup handlers — all run inside an asyncpg transaction passed from the executor.
signup.confirm uses SELECT FOR UPDATE to prevent race conditions on slot capacity.
"""
from typing import Any
from uuid import UUID

import asyncpg


async def confirm(
    conn: asyncpg.Connection,
    args: dict[str, Any],
    caller_id: UUID,
    org_id: UUID,
) -> dict[str, Any]:
    event_id = args["event_id"]
    slot_label = args["slot"]                 # label or partial match
    user_id = args.get("user_id", caller_id)  # organizer can sign up others

    # Resolve slot by label (case-insensitive partial match)
    slot_row = await conn.fetchrow(
        """
        SELECT s.id, s.label, s.capacity, s.filled
        FROM slots s
        JOIN events e ON e.id = s.event_id
        WHERE s.event_id = $1
          AND e.org_id = $2
          AND lower(s.label) LIKE lower($3)
        FOR UPDATE
        """,
        event_id, org_id, f"%{slot_label}%",
    )

    if not slot_row:
        return {"error": f"No slot matching '{slot_label}' found for event {event_id}"}

    slot_id = slot_row["id"]

    # Check for duplicate signup
    existing = await conn.fetchrow(
        "SELECT id, status FROM signups WHERE slot_id=$1 AND user_id=$2",
        slot_id, user_id,
    )
    if existing and existing["status"] != "cancelled":
        return {
            "signup": dict(existing),
            "status": existing["status"],
            "message": "Already signed up for this slot.",
        }

    # Slot full → waitlist
    if slot_row["filled"] >= slot_row["capacity"]:
        next_position = await conn.fetchval(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM waitlist WHERE slot_id=$1",
            slot_id,
        )
        wl_row = await conn.fetchrow(
            """
            INSERT INTO waitlist (slot_id, user_id, position, status)
            VALUES ($1, $2, $3, 'waiting')
            RETURNING id, slot_id, user_id, position, status
            """,
            slot_id, user_id, next_position,
        )
        return {
            "status": "waitlisted",
            "position": next_position,
            "waitlist_entry": dict(wl_row),
            "slot": {"label": slot_row["label"], "capacity": slot_row["capacity"], "filled": slot_row["filled"]},
        }

    # Slot available → confirm
    await conn.execute(
        "UPDATE slots SET filled = filled + 1 WHERE id = $1",
        slot_id,
    )
    signup_row = await conn.fetchrow(
        """
        INSERT INTO signups (slot_id, event_id, user_id, status, channel)
        VALUES ($1, $2, $3, 'confirmed', 'web')
        RETURNING id, slot_id, event_id, user_id, status, channel, created_at
        """,
        slot_id, event_id, user_id,
    )

    return {
        "status": "confirmed",
        "signup": dict(signup_row),
        "slot": {"label": slot_row["label"], "capacity": slot_row["capacity"], "filled": slot_row["filled"] + 1},
    }


async def cancel(
    conn: asyncpg.Connection,
    args: dict[str, Any],
    caller_id: UUID,
    org_id: UUID,
) -> dict[str, Any]:
    signup_id = args["signup_id"]

    # Fetch and lock the signup row
    signup_row = await conn.fetchrow(
        """
        SELECT sg.id, sg.slot_id, sg.event_id, sg.user_id, sg.status
        FROM signups sg
        JOIN events e ON e.id = sg.event_id
        WHERE sg.id = $1 AND e.org_id = $2
        FOR UPDATE
        """,
        signup_id, org_id,
    )

    if not signup_row:
        return {"error": f"Signup {signup_id} not found."}
    if signup_row["status"] == "cancelled":
        return {"message": "Signup already cancelled.", "signup_id": str(signup_id)}

    await conn.execute(
        "UPDATE signups SET status='cancelled' WHERE id=$1",
        signup_id,
    )
    await conn.execute(
        "UPDATE slots SET filled = GREATEST(filled - 1, 0) WHERE id=$1",
        signup_row["slot_id"],
    )

    # Promote top waitlist entry if one exists
    next_wl = await conn.fetchrow(
        """
        SELECT id, user_id FROM waitlist
        WHERE slot_id=$1 AND status='waiting'
        ORDER BY position ASC LIMIT 1
        FOR UPDATE
        """,
        signup_row["slot_id"],
    )
    promoted = None
    if next_wl:
        await conn.execute(
            "UPDATE waitlist SET status='promoted' WHERE id=$1",
            next_wl["id"],
        )
        # Auto-confirm promoted user
        await conn.execute(
            "UPDATE slots SET filled = filled + 1 WHERE id=$1",
            signup_row["slot_id"],
        )
        promo_signup = await conn.fetchrow(
            """
            INSERT INTO signups (slot_id, event_id, user_id, status, channel)
            VALUES ($1, $2, $3, 'confirmed', 'web')
            RETURNING id, user_id, status
            """,
            signup_row["slot_id"], signup_row["event_id"], next_wl["user_id"],
        )
        promoted = dict(promo_signup)

    return {
        "cancelled_signup_id": str(signup_id),
        "promoted_from_waitlist": promoted,
    }


async def list_signups(
    conn: asyncpg.Connection,
    args: dict[str, Any],
    org_id: UUID,
) -> dict[str, Any]:
    event_id = args.get("event_id")
    status_filter = args.get("status", "confirmed")

    conditions = ["e.org_id = $1"]
    values: list[Any] = [org_id]

    if event_id:
        values.append(event_id)
        conditions.append(f"sg.event_id = ${len(values)}")

    if status_filter and status_filter != "all":
        values.append(status_filter)
        conditions.append(f"sg.status = ${len(values)}")

    where = " AND ".join(conditions)
    rows = await conn.fetch(
        f"""
        SELECT sg.id, sg.event_id, sg.slot_id, sg.user_id,
               sg.status, sg.channel, sg.created_at,
               u.display_name, u.email,
               s.label AS slot_label,
               ev.title AS event_title
        FROM signups sg
        JOIN events ev ON ev.id = sg.event_id
        JOIN slots s ON s.id = sg.slot_id
        JOIN users u ON u.id = sg.user_id
        WHERE {where}
        ORDER BY sg.created_at DESC
        """,
        *values,
    )

    return {"signups": [dict(r) for r in rows]}