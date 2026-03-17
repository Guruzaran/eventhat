"""
LAYER 4 — Confirmation Gate
Static lookup table — never an LLM decision.
"""
from models.commands import ConfirmationTier, ParsedCommand

CONFIRMATION_TIERS: dict[str, ConfirmationTier] = {
    # WRITE — reversible state changes
    "event:create":   ConfirmationTier.WRITE,
    "event:update":   ConfirmationTier.WRITE,
    "event:clone":    ConfirmationTier.WRITE,
    "signup:confirm": ConfirmationTier.WRITE,
    "notify:send":    ConfirmationTier.WRITE,
    "payment:link":   ConfirmationTier.WRITE,

    # DESTRUCTIVE — hard to undo
    "signup:cancel":  ConfirmationTier.DESTRUCTIVE,
    "payment:refund": ConfirmationTier.DESTRUCTIVE,

    # READ — pass through immediately, no confirmation card
    "event:show":      ConfirmationTier.READ,
    "event:list":      ConfirmationTier.READ,
    "signup:list":     ConfirmationTier.READ,
    "signup:show":     ConfirmationTier.READ,
    "list:events":     ConfirmationTier.READ,
    "list:signups":    ConfirmationTier.READ,
    "list:waitlist":   ConfirmationTier.READ,
    "show:context":    ConfirmationTier.READ,
    "payment:status":  ConfirmationTier.READ,
}


def classify(cmd: ParsedCommand) -> ConfirmationTier:
    # Special case: event update --status cancelled is DESTRUCTIVE
    if cmd.key == "event:update" and cmd.args.get("status") == "cancelled":
        return ConfirmationTier.DESTRUCTIVE

    return CONFIRMATION_TIERS.get(cmd.key, ConfirmationTier.WRITE)
