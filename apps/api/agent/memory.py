"""
LAYER 2 — Vector Memory
Gemini gemini-embedding-001 → pgvector semantic search + semantic cache.
Embedding dimension: 3072.
"""
import os
from uuid import UUID

import asyncpg
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")
SIMILARITY_THRESHOLD_EVENTS = 0.5
SIMILARITY_THRESHOLD_CACHE  = 0.90


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

async def embed(text: str) -> list[float]:
    """Return a 768-dim embedding vector for the given text."""
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_query",
    )
    return result["embedding"]


# ---------------------------------------------------------------------------
# Semantic event search (context for the system prompt)
# ---------------------------------------------------------------------------

async def search_similar_events(
    org_id: UUID,
    embedding: list[float],
    pool: asyncpg.Pool,
    limit: int = 3,
) -> list[dict]:
    """
    Return up to `limit` events whose embedding is similar to the query.
    Filters out results below SIMILARITY_THRESHOLD_EVENTS (0.5).
    """
    vector_str = f"[{','.join(str(x) for x in embedding)}]"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, title, status, starts_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM events
            WHERE org_id = $2
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) > $3
            ORDER BY embedding <=> $1::vector
            LIMIT $4
            """,
            vector_str,
            org_id,
            SIMILARITY_THRESHOLD_EVENTS,
            limit,
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Semantic cache (skip LLM entirely on near-identical queries)
# ---------------------------------------------------------------------------

async def check_semantic_cache(
    org_id: UUID,
    embedding: list[float],
    pool: asyncpg.Pool,
) -> str | None:
    """
    Return cached CLI result if a near-identical query (similarity >= 0.90)
    exists and has not expired. Increments hit_count on cache hit.
    """
    vector_str = f"[{','.join(str(x) for x in embedding)}]"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, cli_result,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM semantic_cache
            WHERE org_id = $2
              AND expires_at > NOW()
              AND 1 - (embedding <=> $1::vector) >= $3
            ORDER BY embedding <=> $1::vector
            LIMIT 1
            """,
            vector_str,
            org_id,
            SIMILARITY_THRESHOLD_CACHE,
        )
        if not row:
            return None

        await conn.execute(
            "UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = $1",
            row["id"],
        )
        return row["cli_result"]


async def cache_query(
    org_id: UUID,
    query_text: str,
    embedding: list[float],
    cli_result: str,
    pool: asyncpg.Pool,
) -> None:
    """Store a query → CLI result mapping in the semantic cache."""
    vector_str = f"[{','.join(str(x) for x in embedding)}]"

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO semantic_cache (org_id, query_text, embedding, cli_result)
            VALUES ($1, $2, $3::vector, $4)
            ON CONFLICT DO NOTHING
            """,
            org_id,
            query_text,
            vector_str,
            cli_result,
        )
