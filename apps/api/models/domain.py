from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class Organization(BaseModel):
    id: UUID
    name: str
    slug: str
    created_at: datetime


class User(BaseModel):
    id: UUID
    org_id: Optional[UUID] = None
    email: str
    phone: Optional[str] = None
    display_name: str
    role: str  # 'organizer' | 'participant'
    created_at: datetime


class Event(BaseModel):
    id: UUID
    org_id: UUID
    created_by: UUID
    title: str
    description: Optional[str] = None
    event_type: str = "volunteer"     # 'volunteer' | 'paid_ticket'
    status: str = "draft"             # 'draft' | 'published' | 'cancelled'
    starts_at: Optional[datetime] = None
    location: Optional[str] = None
    privacy: str = "public"           # 'public' | 'private'
    recurrence_rule: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class Slot(BaseModel):
    id: UUID
    event_id: UUID
    label: str
    capacity: int
    filled: int = 0
    price_cents: int = 0
    created_at: datetime


class Signup(BaseModel):
    id: UUID
    slot_id: UUID
    event_id: UUID
    user_id: UUID
    status: str = "confirmed"         # 'confirmed' | 'waitlisted' | 'cancelled'
    channel: str = "web"
    created_at: datetime


class WaitlistEntry(BaseModel):
    id: UUID
    slot_id: UUID
    user_id: UUID
    position: int
    status: str = "waiting"
    hold_until: Optional[datetime] = None


class Payment(BaseModel):
    id: UUID
    signup_id: UUID
    stripe_payment_intent_id: Optional[str] = None
    amount_cents: int
    status: str = "pending"
    created_at: datetime


class AISession(BaseModel):
    id: UUID
    user_id: UUID
    messages: list[dict[str, Any]] = []
    active_event_id: Optional[UUID] = None
    last_active_at: datetime
    created_at: datetime


class AuditEntry(BaseModel):
    id: UUID
    session_id: Optional[UUID] = None
    caller_id: UUID
    raw_cli: str
    parsed_verb: Optional[str] = None
    parsed_noun: Optional[str] = None
    parsed_args: Optional[dict[str, Any]] = None
    result_status: Optional[str] = None  # 'success' | 'error' | 'parse_error' | 'replayed'
    result_data: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    created_at: datetime
