import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS organizations (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT NOT NULL,
  slug       TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       UUID REFERENCES organizations(id),
  email        TEXT UNIQUE NOT NULL,
  phone        TEXT,
  display_name TEXT NOT NULL,
  role         TEXT CHECK(role IN ('organizer','participant')) DEFAULT 'organizer',
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID REFERENCES organizations(id),
  created_by      UUID REFERENCES users(id),
  title           TEXT NOT NULL,
  description     TEXT,
  event_type      TEXT CHECK(event_type IN ('volunteer','paid_ticket')) DEFAULT 'volunteer',
  status          TEXT CHECK(status IN ('draft','published','cancelled')) DEFAULT 'draft',
  starts_at       TIMESTAMPTZ,
  location        TEXT,
  privacy         TEXT CHECK(privacy IN ('public','private')) DEFAULT 'public',
  recurrence_rule JSONB,
  embedding       vector(768),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS slots (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id    UUID REFERENCES events(id) ON DELETE CASCADE,
  label       TEXT NOT NULL,
  capacity    INTEGER NOT NULL CHECK(capacity > 0),
  filled      INTEGER DEFAULT 0 CHECK(filled >= 0),
  price_cents INTEGER DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signups (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slot_id    UUID REFERENCES slots(id),
  event_id   UUID REFERENCES events(id),
  user_id    UUID REFERENCES users(id),
  status     TEXT CHECK(status IN ('confirmed','waitlisted','cancelled')) DEFAULT 'confirmed',
  channel    TEXT DEFAULT 'web',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(slot_id, user_id)
);

CREATE TABLE IF NOT EXISTS waitlist (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slot_id    UUID REFERENCES slots(id),
  user_id    UUID REFERENCES users(id),
  position   INTEGER NOT NULL,
  status     TEXT DEFAULT 'waiting',
  hold_until TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS payments (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signup_id                UUID REFERENCES signups(id),
  stripe_payment_intent_id TEXT,
  amount_cents             INTEGER NOT NULL,
  status                   TEXT DEFAULT 'pending',
  created_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id),
  messages        JSONB DEFAULT '[]',
  active_event_id UUID REFERENCES events(id),
  last_active_at  TIMESTAMPTZ DEFAULT NOW(),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id    UUID REFERENCES ai_sessions(id),
  caller_id     UUID REFERENCES users(id),
  raw_cli       TEXT NOT NULL,
  parsed_verb   TEXT,
  parsed_noun   TEXT,
  parsed_args   JSONB,
  result_status TEXT CHECK(result_status IN ('success','error','parse_error','replayed')),
  result_data   JSONB,
  error_code    TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

CREATE TABLE IF NOT EXISTS semantic_cache (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     UUID REFERENCES organizations(id),
  query_text TEXT NOT NULL,
  embedding  vector(768) NOT NULL,
  cli_result TEXT NOT NULL,
  hit_count  INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

CREATE INDEX IF NOT EXISTS idx_events_org_status ON events(org_id, status);
CREATE INDEX IF NOT EXISTS idx_slots_event ON slots(event_id);
CREATE INDEX IF NOT EXISTS idx_signups_event ON signups(event_id);
CREATE INDEX IF NOT EXISTS idx_signups_user ON signups(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_caller ON audit_log(caller_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_sessions_user ON ai_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_events_embedding ON events USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_semantic_cache_embedding ON semantic_cache USING hnsw (embedding vector_cosine_ops);
"""


async def run_migrations():
    conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
    try:
        await conn.execute(SQL)
        print("Migration complete, pgvector ready")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
