import shlex
from datetime import date, datetime
from typing import Union

from models.commands import ConfirmationTier, ParsedCommand, ParseError, SlotConfig
from lib.rbac import check_rbac

# ---------------------------------------------------------------------------
# Grammar definition
# ---------------------------------------------------------------------------

VALID_NOUNS: dict[str, set[str]] = {
    "event":   {"create", "update", "show", "list", "clone"},
    "signup":  {"confirm", "cancel", "list", "show"},
    "notify":  {"send"},
    "payment": {"link", "status", "refund"},
    "list":    {"events", "signups", "waitlist"},
    "show":    {"context"},
}

# Required flags per verb:noun
REQUIRED_FLAGS: dict[str, list[str]] = {
    "event:create": ["title", "date", "slots"],
    "event:update": ["event_id"],
    "event:show":   ["event_id"],
    "event:clone":  ["event_id"],
    "signup:confirm": ["event_id", "slot"],
    "signup:cancel":  ["signup_id"],
    "signup:show":    ["signup_id"],
    "notify:send":    ["event_id", "type"],
    "payment:link":   ["signup_id"],
    "payment:status": ["signup_id"],
    "payment:refund": ["signup_id"],
}

# Allowed flags per verb:noun (includes optional ones)
ALLOWED_FLAGS: dict[str, set[str]] = {
    "event:create":  {"title", "date", "slots", "location", "price", "privacy", "description", "type"},
    "event:update":  {"event_id", "title", "date", "slots", "location", "price", "privacy", "status", "description"},
    "event:show":    {"event_id"},
    "event:list":    {"status", "privacy"},
    "event:clone":   {"event_id", "date"},
    "signup:confirm":{"event_id", "slot", "user_id"},
    "signup:cancel": {"signup_id"},
    "signup:list":   {"event_id", "status"},
    "signup:show":   {"signup_id"},
    "notify:send":   {"event_id", "type", "message"},
    "payment:link":  {"signup_id"},
    "payment:status":{"signup_id"},
    "payment:refund":{"signup_id"},
    "list:events":   {"status", "privacy"},
    "list:signups":  {"event_id", "status"},
    "list:waitlist": {"event_id"},
    "show:context":  set(),
}

# Confirmation tiers (READ commands need no confirmation)
READ_COMMANDS = {
    "event:show", "event:list",
    "signup:list", "signup:show",
    "list:events", "list:signups", "list:waitlist",
    "show:context",
}

DESTRUCTIVE_COMMANDS = {
    "signup:cancel",
    "payment:refund",
}

# Valid enum values
STATUS_EVENT    = {"draft", "published", "cancelled"}
STATUS_SIGNUP   = {"confirmed", "waitlisted", "cancelled", "all"}
PRIVACY_VALUES  = {"public", "private"}
NOTIFY_TYPES    = {"reminder-48h", "reminder-2h", "custom", "cancellation", "waitlist-open"}
EVENT_TYPES     = {"volunteer", "paid_ticket"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_date(value: str, field: str) -> Union[str, ParseError]:
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return ParseError(
            error_code="TYPE_ERROR",
            message=f"--{field} must be a date in YYYY-MM-DD format, got '{value}'",
            field=field,
        )
    if d <= date.today():
        return ParseError(
            error_code="TYPE_ERROR",
            message=f"--{field} must be a future date, got '{value}'",
            field=field,
        )
    return value


def _coerce_slots(value: str) -> Union[SlotConfig, ParseError]:
    try:
        if "x" in value.lower():
            parts = value.lower().split("x")
            if len(parts) != 2:
                raise ValueError
            count, capacity = int(parts[0]), int(parts[1])
        else:
            count, capacity = 1, int(value)
        if count < 1 or capacity < 1:
            raise ValueError
        return SlotConfig(count=count, capacity=capacity)
    except (ValueError, TypeError):
        return ParseError(
            error_code="TYPE_ERROR",
            message=f"--slots must be NxM (e.g. 3x10) or N (e.g. 20), got '{value}'",
            field="slots",
        )


def _coerce_price(value: str) -> Union[int, ParseError]:
    try:
        cents = round(float(value) * 100)
        if cents < 0:
            raise ValueError
        return cents
    except (ValueError, TypeError):
        return ParseError(
            error_code="TYPE_ERROR",
            message=f"--price must be a decimal number like 25.00, got '{value}'",
            field="price",
        )


def _classify_tier(key: str, args: dict) -> ConfirmationTier:
    if key == "event:update" and args.get("status") == "cancelled":
        return ConfirmationTier.DESTRUCTIVE
    if key in DESTRUCTIVE_COMMANDS:
        return ConfirmationTier.DESTRUCTIVE
    if key in READ_COMMANDS:
        return ConfirmationTier.READ
    return ConfirmationTier.WRITE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(raw_cli: str, role: str = "organizer") -> Union[ParsedCommand, ParseError]:
    raw_cli = raw_cli.strip()

    # Handle special LLM prefixes — surface as clarification errors
    if raw_cli.upper().startswith("ASK:"):
        return ParseError(
            error_code="PARSE_ERROR",
            message=raw_cli[4:].strip(),
            is_clarification=True,
        )
    if raw_cli.upper().startswith("UNSUPPORTED:"):
        return ParseError(
            error_code="PARSE_ERROR",
            message=raw_cli[12:].strip(),
        )

    # Tokenise safely (handles quoted strings)
    try:
        tokens = shlex.split(raw_cli)
    except ValueError as e:
        return ParseError(error_code="PARSE_ERROR", message=f"Could not parse command: {e}")

    if len(tokens) < 2:
        return ParseError(error_code="PARSE_ERROR", message="Command must have at least a verb and a noun.")

    verb, noun = tokens[0].lower(), tokens[1].lower()

    # Verb check
    if verb not in VALID_NOUNS:
        return ParseError(
            error_code="INVALID_VERB",
            message=f"Unknown verb '{verb}'. Valid verbs: {', '.join(sorted(VALID_NOUNS))}",
        )

    # Noun check
    if noun not in VALID_NOUNS[verb]:
        return ParseError(
            error_code="INVALID_NOUN",
            message=f"Unknown noun '{noun}' for verb '{verb}'. Valid: {', '.join(sorted(VALID_NOUNS[verb]))}",
        )

    key = f"{verb}:{noun}"

    # RBAC check
    if not check_rbac(role, key):
        return ParseError(
            error_code="ROLE_INSUFFICIENT",
            message=f"Your role '{role}' is not permitted to run '{key}'.",
        )

    # Flag parsing
    allowed = ALLOWED_FLAGS.get(key, set())
    raw_args: dict = {}
    flag_tokens = tokens[2:]
    i = 0

    while i < len(flag_tokens):
        token = flag_tokens[i]
        if token.startswith("--"):
            flag = token[2:]
            if flag not in allowed:
                return ParseError(
                    error_code="UNKNOWN_FLAG",
                    message=f"Unknown flag '--{flag}' for '{key}'. Allowed: {', '.join(f'--{f}' for f in sorted(allowed))}",
                    field=flag,
                )
            # Value is next token (if not another flag)
            if i + 1 < len(flag_tokens) and not flag_tokens[i + 1].startswith("--"):
                raw_args[flag] = flag_tokens[i + 1]
                i += 2
            else:
                raw_args[flag] = True  # boolean flag
                i += 1
        else:
            return ParseError(
                error_code="PARSE_ERROR",
                message=f"Unexpected token '{token}'. Flags must start with '--'.",
            )

    # Required flag check
    for req in REQUIRED_FLAGS.get(key, []):
        if req not in raw_args:
            return ParseError(
                error_code="MISSING_REQUIRED",
                message=f"Missing required flag '--{req}' for '{key}'.",
                field=req,
            )

    # Type coercion
    args: dict = {}
    for flag, value in raw_args.items():
        if flag == "date":
            result = _coerce_date(value, "date")
            if isinstance(result, ParseError):
                return result
            args[flag] = result

        elif flag == "slots":
            result = _coerce_slots(value)
            if isinstance(result, ParseError):
                return result
            args[flag] = result

        elif flag == "price":
            result = _coerce_price(value)
            if isinstance(result, ParseError):
                return result
            args[flag] = result

        elif flag == "status":
            pool = STATUS_EVENT if verb == "event" else STATUS_SIGNUP
            if value not in pool:
                return ParseError(
                    error_code="TYPE_ERROR",
                    message=f"--status '{value}' is invalid. Allowed: {', '.join(sorted(pool))}",
                    field="status",
                )
            args[flag] = value

        elif flag == "privacy":
            if value not in PRIVACY_VALUES:
                return ParseError(
                    error_code="TYPE_ERROR",
                    message=f"--privacy must be 'public' or 'private', got '{value}'",
                    field="privacy",
                )
            args[flag] = value

        elif flag == "type":
            # Disambiguate: event type vs notify type
            if verb == "event":
                if value not in EVENT_TYPES:
                    return ParseError(
                        error_code="TYPE_ERROR",
                        message=f"--type must be 'volunteer' or 'paid_ticket', got '{value}'",
                        field="type",
                    )
            elif verb == "notify":
                if value not in NOTIFY_TYPES:
                    return ParseError(
                        error_code="TYPE_ERROR",
                        message=f"--type must be one of {', '.join(sorted(NOTIFY_TYPES))}, got '{value}'",
                        field="type",
                    )
            args[flag] = value

        else:
            args[flag] = value

    tier = _classify_tier(key, args)

    return ParsedCommand(
        verb=verb,
        noun=noun,
        args=args,
        raw_cli=raw_cli,
        key=key,
        requires_confirmation=(tier != ConfirmationTier.READ),
        confirmation_tier=tier,
    )
