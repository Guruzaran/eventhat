"""
Response formatter — typed ExecutionResult → human-readable markdown string.
NO second LLM call. Template-based only.
"""
from typing import Any

from models.commands import ExecutionResult, ParsedCommand


def format_response(cmd: ParsedCommand, result: ExecutionResult) -> str:
    text = _template(cmd, result.data)
    if result.replayed:
        text += "\n\n_(already done — showing cached result)_"
    return text


def _template(cmd: ParsedCommand, data: dict[str, Any]) -> str:
    key = cmd.key

    # -----------------------------------------------------------------------
    # Event
    # -----------------------------------------------------------------------
    if key == "event:create":
        ev = data.get("event", {})
        slots = data.get("slots", [])
        slot_lines = "\n".join(
            f"  - **{s['label']}** — {s['capacity']} spots"
            for s in slots
        )
        return (
            f"Event **{ev.get('title')}** created successfully.\n\n"
            f"- Status: `{ev.get('status', 'draft')}`\n"
            f"- Date: {ev.get('starts_at', 'not set')}\n"
            f"- Privacy: {ev.get('privacy', 'public')}\n\n"
            f"**Slots ({len(slots)}):**\n{slot_lines}"
        )

    if key == "event:update":
        ev = data.get("event", {})
        return (
            f"Event updated.\n\n"
            f"- Status: `{ev.get('status', 'unchanged')}`\n"
            f"- Last updated: {ev.get('updated_at', '')}"
        )

    if key == "event:show":
        ev = data.get("event")
        if not ev:
            return "Event not found."
        slots = data.get("slots", [])
        slot_lines = "\n".join(
            f"  - **{s['label']}** — {s['filled']}/{s['capacity']} filled"
            for s in slots
        )
        return (
            f"## {ev['title']}\n\n"
            f"- Status: `{ev.get('status')}`\n"
            f"- Date: {ev.get('starts_at', 'not set')}\n"
            f"- Location: {ev.get('location', 'not set')}\n"
            f"- Privacy: {ev.get('privacy')}\n\n"
            f"**Slots:**\n{slot_lines}"
        )

    if key in ("event:list", "list:events"):
        events = data.get("events", [])
        if not events:
            return "No events found."
        lines = [
            f"- **{e['title']}** — `{e['status']}` — {e.get('starts_at', 'no date')}"
            for e in events
        ]
        return f"Found **{len(events)}** event(s):\n\n" + "\n".join(lines)

    # -----------------------------------------------------------------------
    # Signup
    # -----------------------------------------------------------------------
    if key == "signup:confirm":
        status = data.get("status")
        slot = data.get("slot", {})
        if status == "waitlisted":
            return (
                f"The **{slot.get('label', 'selected')}** slot is full "
                f"({slot.get('filled')}/{slot.get('capacity')}).\n\n"
                f"You've been added to the waitlist at position **{data.get('position')}**."
            )
        return (
            f"Signed up successfully!\n\n"
            f"- Slot: **{slot.get('label', 'General')}**\n"
            f"- Spots filled: {slot.get('filled')}/{slot.get('capacity')}\n"
            f"- Status: `confirmed`"
        )

    if key == "signup:cancel":
        promoted = data.get("promoted_from_waitlist")
        msg = "Signup cancelled successfully."
        if promoted:
            msg += "\n\nA participant from the waitlist has been automatically confirmed."
        return msg

    if key in ("signup:list", "list:signups"):
        signups = data.get("signups", [])
        if not signups:
            return "No signups found."
        lines = [
            f"- **{s['display_name']}** ({s['email']}) — {s['slot_label']} — `{s['status']}`"
            for s in signups
        ]
        return f"**{len(signups)}** signup(s):\n\n" + "\n".join(lines)

    # -----------------------------------------------------------------------
    # Context
    # -----------------------------------------------------------------------
    if key == "show:context":
        events = data.get("events", [])
        if not events:
            return "No events in your organisation yet."
        lines = [
            f"- **{e['title']}** — `{e['status']}`"
            for e in events
        ]
        return f"Your organisation has **{len(events)}** event(s):\n\n" + "\n".join(lines)

    return "Done."
