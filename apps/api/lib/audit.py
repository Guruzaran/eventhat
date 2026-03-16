import json
from typing import Any
from uuid import UUID

import asyncpg


async def write_audit(
    conn: asyncpg.Connection,
    session_id: UUID | None,
    caller_id: UUID,
    raw_cli: str,
    parsed_verb: str | None,
    parsed_noun: str | None,
    parsed_args: dict[str, Any] | None,
    result_status: str,           # 'success' | 'error' | 'parse_error' | 'replayed'
    result_data: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> None:
    """
    Insert one row into audit_log using the connection/transaction passed in.
    MUST be called inside the same transaction as the execution — never open
    a new connection here.
    """
    await conn.execute(
        """
        INSERT INTO audit_log (
            session_id, caller_id, raw_cli,
            parsed_verb, parsed_noun, parsed_args,
            result_status, result_data, error_code
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        session_id,
        caller_id,
        raw_cli,
        parsed_verb,
        parsed_noun,
        json.dumps(parsed_args, default=str) if parsed_args is not None else None,
        result_status,
        json.dumps(result_data, default=str) if result_data is not None else None,
        error_code,
    )