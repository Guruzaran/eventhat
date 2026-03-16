from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum


class ConfirmationTier(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class SlotConfig(BaseModel):
    count: int
    capacity: int


class ParsedCommand(BaseModel):
    verb: str
    noun: str
    args: dict[str, Any]
    raw_cli: str
    key: str                          # "verb:noun"
    requires_confirmation: bool
    confirmation_tier: ConfirmationTier


class ParseError(BaseModel):
    ok: bool = False
    error_code: str                   # INVALID_VERB | INVALID_NOUN | MISSING_REQUIRED
                                      # UNKNOWN_FLAG | TYPE_ERROR | PARSE_ERROR
                                      # ROLE_INSUFFICIENT
    message: str                      # user-facing explanation
    field: Optional[str] = None       # which flag failed (for TYPE_ERROR)
    is_clarification: bool = False    # True when LLM returned ASK:


class ExecutionResult(BaseModel):
    data: dict[str, Any]
    message: str
    replayed: bool = False            # True when served from idempotency cache
