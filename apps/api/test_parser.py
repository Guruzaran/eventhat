import sys
sys.path.insert(0, ".")

from agent.parser import parse
from models.commands import ParsedCommand, ParseError

# --- PASS cases ---
r = parse("event create --title 'Test' --date 2027-04-01 --slots 3x10")
assert isinstance(r, ParsedCommand), f"Expected ParsedCommand, got {r}"
assert r.verb == "event"
assert r.noun == "create"
assert r.args["slots"].count == 3
assert r.args["slots"].capacity == 10

r = parse("signup confirm --event_id abc --slot morning")
assert isinstance(r, ParsedCommand), f"Expected ParsedCommand, got {r}"
assert r.verb == "signup"

r = parse("show context")
assert isinstance(r, ParsedCommand), f"Expected ParsedCommand, got {r}"
assert r.key == "show:context"
assert r.requires_confirmation == False

# --- FAIL cases ---
r = parse("event creat --title x")
assert isinstance(r, ParseError), f"Expected ParseError, got {r}"
assert r.error_code == "INVALID_NOUN", f"Got {r.error_code}"

r = parse("event create --title x")
assert isinstance(r, ParseError), f"Expected ParseError, got {r}"
assert r.error_code == "MISSING_REQUIRED", f"Got {r.error_code}"

r = parse("event create --title x --date 2020-01-01 --slots 3x10")
assert isinstance(r, ParseError), f"Expected ParseError, got {r}"
assert r.error_code == "TYPE_ERROR", f"Got {r.error_code}"

r = parse("event create --title x --date 2027-04-01 --slots abc")
assert isinstance(r, ParseError), f"Expected ParseError, got {r}"
assert r.error_code == "TYPE_ERROR", f"Got {r.error_code}"

r = parse("event create --title x --date 2027-04-01 --slots 3x10 --foo bar")
assert isinstance(r, ParseError), f"Expected ParseError, got {r}"
assert r.error_code == "UNKNOWN_FLAG", f"Got {r.error_code}"

# --- RBAC ---
r = parse("event create --title x --date 2027-04-01 --slots 3x10", role="participant")
assert isinstance(r, ParseError), f"Expected ParseError, got {r}"
assert r.error_code == "ROLE_INSUFFICIENT", f"Got {r.error_code}"

# --- Confirmation tiers ---
r = parse("signup cancel --signup_id abc")
assert isinstance(r, ParsedCommand)
assert r.confirmation_tier.value == "DESTRUCTIVE"

r = parse("event update --event_id abc --status cancelled")
assert isinstance(r, ParsedCommand)
assert r.confirmation_tier.value == "DESTRUCTIVE"

r = parse("event create --title 'x' --date 2027-04-01 --slots 3x10")
assert isinstance(r, ParsedCommand)
assert r.confirmation_tier.value == "WRITE"

# --- Price coercion ---
r = parse("event create --title 'Paid Event' --date 2027-04-01 --slots 1x50 --price 25.00")
assert isinstance(r, ParsedCommand)
assert r.args["price"] == 2500

print("All parser tests passed")
