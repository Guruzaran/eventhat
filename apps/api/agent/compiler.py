"""
LAYER 2 — Intent Compiler
Converts natural language → ONE CLI command string using Gemini 1.5 Flash.
This is the ONLY place in the system that calls the LLM.
"""
import os
from datetime import date
from uuid import UUID

import asyncpg
import google.generativeai as genai
from dotenv import load_dotenv
from redis.asyncio import Redis

from agent.memory import (
    cache_query,
    check_semantic_cache,
    embed,
    search_similar_events,
)
from agent.prompts import CLI_GRAMMAR, FEW_SHOT_EXAMPLES

load_dotenv()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

LLM_MODEL = "models/gemini-2.5-flash"



def _build_system_prompt(caller_ctx: dict, similar_events: list[dict]) -> str:
    today = date.today().isoformat()
    role = caller_ctx.get("role", "organizer")
    org_name = caller_ctx.get("org_name", "your organisation")
    active_event_id = caller_ctx.get("active_event_id", "UNKNOWN")

    similar_section = ""
    if similar_events:
        lines = [
            f"  - {e['title']} (status: {e['status']}, id: {e['id']})"
            for e in similar_events
        ]
        similar_section = "Recent similar events in your org:\n" + "\n".join(lines)

    examples = FEW_SHOT_EXAMPLES.format(
        next_saturday="NEXT_SATURDAY",
        active_event_id=active_event_id,
    )

    return f"""You are the intent compiler for Eventhat, an event coordination platform.
Organisation: {org_name}
Caller role: {role}
Today's date: {today}
Active event ID: {active_event_id}

{similar_section}

CLI GRAMMAR (the ONLY valid output format):
{CLI_GRAMMAR}

Examples:
{examples}

Rules:
- Output ONE CLI command line only.
- No explanation. No JSON. No markdown. No code blocks.
- If intent is ambiguous, output: ASK:<your question>
- If request is outside platform scope, output: UNSUPPORTED:<reason>
- Always use ISO-8601 dates (YYYY-MM-DD).
- Never invent event_ids or signup_ids — use the active_event_id or output ASK:
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compile(
    message: str,
    conversation_history: list[dict],
    caller_ctx: dict,
    pool: asyncpg.Pool,
    redis: Redis,
) -> str:
    """
    Convert a natural language message to a single CLI command string.

    Pipeline:
    1. Embed the message
    2. Check semantic cache (skip LLM if near-identical query seen before)
    3. Search similar events (for system prompt context)
    4. Call Gemini 1.5 Flash (temp=0.0)
    5. Cache the result
    6. Return raw CLI string
    """
    org_id: UUID = caller_ctx["org_id"]

    # Step 1: Embed
    embedding = await embed(message)

    # Step 2: Semantic cache check
    cached_cli = await check_semantic_cache(org_id, embedding, pool)
    if cached_cli:
        return cached_cli

    # Step 3: Similar events for context
    similar_events = await search_similar_events(org_id, embedding, pool)

    # Step 4: Build prompt + call Gemini
    system_prompt = _build_system_prompt(caller_ctx, similar_events)

    # Build conversation turns for Gemini
    contents = []
    for msg in conversation_history[-10:]:   # last 10 messages for context
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    # Add current user message
    contents.append({"role": "user", "parts": [{"text": message}]})

    model = genai.GenerativeModel(
        model_name=LLM_MODEL,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.0,          # REQUIRED — deterministic for idempotency keys
            max_output_tokens=150,
            stop_sequences=["\n"],    # enforce single line output
        ),
    )

    response = model.generate_content(contents)
    raw_cli = response.text.strip().split("\n")[0].strip()

    # Step 5: Cache (only for concrete commands, not ASK/UNSUPPORTED)
    if not raw_cli.upper().startswith("ASK:") and not raw_cli.upper().startswith("UNSUPPORTED:"):
        await cache_query(org_id, message, embedding, raw_cli, pool)

    # Step 6: Return
    return raw_cli
