# Eventhat — Claude Code Guidelines

## What this project is

Eventhat is an event coordination platform. The backend is a FastAPI (Python) API at `apps/api/`.
The entire AI surface is a **6-layer agent pipeline** invoked by `POST /chat`. Every other design decision exists to serve that pipeline safely.

---

## The Pipeline — sacred contract

```
User message
  → [1] Session      agent/session.py       load history, get/create session
  → [2] Compiler     agent/compiler.py      NL → single CLI string (Gemini only here)
  → [3] Parser       agent/parser.py        CLI string → ParsedCommand or ParseError
  → [4] Gate         agent/gate.py          READ / WRITE / DESTRUCTIVE  (static, no LLM)
  → [5] Executor     agent/executor.py      dispatch → handler, idempotency, audit
  → [6] Formatter    agent/formatter.py     typed result → markdown string
```

**Rules that must never be violated:**
- Gemini is called **only** in Layer 2 (compiler + embed). No other layer touches the LLM.
- The Gate (Layer 4) is a **static lookup table**. It must never call an LLM or contain branching logic beyond the current special-case for `event:update --status cancelled`.
- Handlers (`handlers/`) run **inside** the asyncpg transaction passed from the executor. They must never open a new connection or start a nested transaction.
- The audit log is written **inside the same transaction** as the domain write. If the write rolls back, the audit rolls back with it.
- Confirmation tokens use **atomic `GETDEL`** (`session.consume_confirmation`). Never replace this with a GET + separate DELETE.

---

## Known gaps — fix these when touching related code

These are real bugs or production gaps discovered by reading the codebase. Fix the one you're near; don't fix all of them speculatively.

### Bug: handlers return error dicts instead of raising DomainError
`handlers/signup.py::confirm()` and `cancel()` return `{"error": "..."}` dicts on not-found cases.
The executor does not inspect return values for errors — it treats any return as success and writes a success audit entry.
**Fix:** raise `DomainError` (imported from `agent/executor.py`) instead of returning error dicts.

### Bug: blocking Gemini calls in async functions
`agent/memory.py::embed()` and `agent/compiler.py::compile()` call `genai.embed_content()` and `model.generate_content()` — both are synchronous, blocking the event loop.
**Fix:** wrap in `asyncio.to_thread(...)`.

### Bug: `genai.configure()` called in two modules
Both `agent/compiler.py` and `agent/memory.py` call `genai.configure(api_key=...)` at module load time.
**Fix:** call once in `main.py` startup, remove from individual modules.

### Bug: `isinstance` vs `hasattr` for ParseError detection
`routes/chat.py` line 164: `if hasattr(parsed, "error_code")` — fragile duck-typing.
**Fix:** `from models.commands import ParseError` and use `isinstance(parsed, ParseError)`.

### Bug: duplicate message-building
`executor.py::_build_message()` and `formatter.py::_template()` produce the same content for the same commands. On idempotency replay (`replayed=True`) the message comes from `_build_message` via the Redis cache, not from `formatter`. This means replay messages have a different format.
**Fix:** store the formatted message in the idempotency cache, or remove `_build_message` and use `formatter` for both paths.

### Gap: missing handlers
The following commands appear in the grammar, Gate, and RBAC, but `executor._route()` raises `NOT_IMPLEMENTED`:
- `event:clone`
- `notify:send`
- `payment:link`, `payment:status`, `payment:refund`
- `signup:show`
- `list:waitlist`

When adding a handler, add it to `executor._route()`, create the function in the appropriate `handlers/` file, and add a formatter template in `formatter.py`.

### Gap: no input validation on `/chat`
`ChatRequest.message` has no max length or empty-string validation.
**Fix:** add `message: str = Field(..., min_length=1, max_length=2000)` using Pydantic's `Field`.

### Gap: `on_event` is deprecated
`main.py` uses `@app.on_event("startup")` — deprecated since FastAPI 0.93.
**Fix:** replace with a `lifespan` async context manager (`@asynccontextmanager` + `app = FastAPI(lifespan=lifespan)`).

### Gap: no versioned migrations
`db/migrate.py` runs raw DDL idempotently. Fine for early development but breaks when schema changes are needed.
**Fix (when schema changes are required):** adopt Alembic. Keep `migrate.py` as a reference; do not delete it until Alembic is fully set up.

### Gap: session messages column grows unboundedly
`ai_sessions.messages` is a JSONB array that appends forever. `get_messages()` trims to 20 on read, but the column keeps all history.
**Fix:** add a trim step in `add_message()` — after appending, trim the stored array to the last 40 entries.

---

## Coding standards

### Python
- Python 3.12. Use built-in generics (`list[str]`, `dict[str, Any]`, `X | Y`) — no `from __future__ import annotations` needed.
- No wildcard imports. Import only what you use.
- Async all the way: every function that touches DB, Redis, or external network must be `async def`.
- Do not use `global` for new state. The existing `_pool` and `_redis` globals are legacy — don't add more.

### FastAPI
- Use `Depends()` for pool injection (already done). Don't call `get_pool()` directly inside route handlers.
- Response models: prefer returning plain dicts for now; don't add Pydantic response models unless the endpoint is part of a public contract.
- HTTP status codes: use `HTTPException` with correct codes — 401 for unauthenticated, 403 for RBAC failure, 410 for expired confirmation, 404 for not found.

### asyncpg
- Always use `pool.acquire()` as a context manager (`async with pool.acquire() as conn`).
- Always use `conn.transaction()` for writes (`async with conn.transaction()`).
- Parameterised queries only — no f-string interpolation of user-supplied values into SQL.
  - The f-string in `event.update()` is safe **only** because the column names come from a hardcoded `updatable` dict. Do not replicate this pattern for anything involving user input.
- Use `SELECT … FOR UPDATE` when you need to lock rows before a write (see `signup.confirm`, `signup.cancel`).

### Error handling
- Domain errors raised from handlers → `DomainError(message, code)` from `agent/executor.py`.
- Parse errors → return a `ParseError` model (not raise).
- Never swallow exceptions. Let them propagate to the executor's `except Exception` block which writes an error audit entry.
- Don't return `{"error": "..."}` dicts from handlers — raise `DomainError`.

### Redis keys — naming convention
```
confirm:{uuid}      — confirmation token (TTL 600s)
idem:{sha256}       — idempotency cache (TTL 3600s)
tx_id:{session_id}  — per-session transaction counter (TTL 7200s)
```
Stick to this convention. Document new keys here if added.

---

## Security rules

- **No password in login** — intentional (email-only, dev-mode magic). Do not add password hashing; add a proper auth provider (magic link / OAuth) when hardening for production.
- **Session cookie** — `SESSION_SECRET` must be a random 32+ byte secret in production. The `https_only=False` flag in `main.py` **must** be flipped to `True` in production.
- **CORS** — `allow_origins` is hardcoded to `localhost:3000`. Move to an env var before deploying.
- **Rate limiting** — `/chat` has no rate limit. Add before any public deployment (e.g. `slowapi` or a gateway rule).
- **Audit log is append-only** — `REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC` is in the schema. Do not remove it. Do not add UPDATE/DELETE paths to `audit_log` in handlers.
- **RBAC is enforced in the parser** — every new command key must be added to `lib/rbac.py::PERMISSIONS` for every role that should have access. Omitting a key means the command is denied for all roles.

---

## Adding a new command

Follow these steps in order — touching all layers is required:

1. **Grammar** — add verb/noun to `VALID_NOUNS`, `REQUIRED_FLAGS`, `ALLOWED_FLAGS` in `agent/parser.py`.
2. **Gate** — add the `"verb:noun": ConfirmationTier.X` entry in `agent/gate.py::CONFIRMATION_TIERS`.
3. **RBAC** — add the key to `lib/rbac.py::PERMISSIONS` for each permitted role.
4. **Prompts** — add a few-shot example to `agent/prompts.py::FEW_SHOT_EXAMPLES`.
5. **Handler** — add the function to the appropriate `handlers/` file. It receives a `conn`, `args`, `caller_id`, `org_id` and must return a plain dict.
6. **Executor router** — add the `if key == "verb:noun":` branch in `executor._route()`.
7. **Formatter** — add the template branch in `formatter._template()`.
8. **Tests** — add unit tests for the parser (valid + error cases) and the handler (use a real test DB, not mocks).

---

## Testing

- **Never mock the database.** Use a real PostgreSQL + pgvector test database. The schema is in `db/migrate.py`.
- **Never mock Redis.** Use a real Redis instance (or `fakeredis` for unit-only tests, but note the caveat above).
- Parser tests (`agent/parser.py`) are pure-Python and should be fast unit tests.
- Handler tests must run inside a rolled-back transaction — use `asyncpg`'s `conn.transaction()` + rollback in test teardown.
- Test the full pipeline through `routes/chat.py` with an ASGI test client (`httpx.AsyncClient` + `ASGITransport`) for integration tests.

---

## What NOT to do

- Do not add a second LLM call anywhere outside `agent/compiler.py`.
- Do not change the Gate to be dynamic or LLM-driven.
- Do not open DB connections or start transactions inside `handlers/` — the connection comes from the executor.
- Do not add `print()` statements — use Python's `logging` module.
- Do not add new global singletons. Pass dependencies via FastAPI's `Depends()` or function arguments.
- Do not add Alembic migration files that ALTER existing columns without a matching backfill — this is a production database.
- Do not store secrets in code. All secrets go in `.env` (local) or environment variables (production).

---

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | asyncpg DSN: `postgresql://user:pass@host/db` |
| `REDIS_URL` | Yes | e.g. `redis://localhost:6379` |
| `GEMINI_API_KEY` | Yes | Google AI Studio key |
| `SESSION_SECRET` | Yes | Random string, min 32 chars in production |
| `GEMINI_EMBEDDING_MODEL` | No | Defaults to `models/text-embedding-004` |

Copy `.env.example` to `.env` before running locally. Never commit `.env`.
