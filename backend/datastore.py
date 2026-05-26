"""Shared data layer for the modes framework.

`backend` is a generic data-accessibility framework: an internal operational
backend with Postgres behind it, exposing a small set of uniform modes. This
module is the shared layer every mode builds on:

- the asyncpg connection pool (`connect` / `close` / `_database_url` / `_init_conn`),
- the `require_token` bearer-auth dependency every mode route depends on,
- the `sentinels` table and `register_sentinel` upsert helper.

Design: coilysiren/backend#65, coilysiren/backend#77, coilysiren/agentic-os-kai#657.
"""

import json
import os
import secrets
import typing

import asyncpg
import fastapi
import fastapi.security
import structlog

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None

# Shared sentinel registry: one row per mode describing its record shape.
# GET /health returns every sentinel.
_SENTINEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentinels (
    mode TEXT PRIMARY KEY,
    shape JSONB NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_bearer = fastapi.security.HTTPBearer(auto_error=False)


def require_token(
    creds: fastapi.security.HTTPAuthorizationCredentials | None = fastapi.Depends(_bearer),
) -> None:
    """Validate the `Authorization: Bearer <token>` header against DATASTORE_TOKEN.

    Fails closed: if no token is configured the route is unavailable rather
    than open. The backend holds personal data, so reads are authed too.
    """
    expected = os.getenv("DATASTORE_TOKEN")
    if not expected:
        raise fastapi.HTTPException(status_code=503, detail="datastore auth not configured")
    if creds is None or not secrets.compare_digest(creds.credentials, expected):
        raise fastapi.HTTPException(status_code=401, detail="invalid or missing bearer token")


def _database_url() -> str:
    """Resolve the Postgres DSN.

    Prefers a full DATABASE_URL; otherwise assembles one from discrete PG*
    parts so the k8s manifest can inject the password as its own secret.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = os.getenv("PGUSER", "backend")
    password = os.getenv("PGPASSWORD", "backend")
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    name = os.getenv("PGDATABASE", "backend")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


async def _init_conn(conn: asyncpg.Connection) -> None:
    """Round-trip jsonb as native Python dicts instead of raw strings."""
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def connect() -> None:
    """Open the connection pool and ensure the sentinel table exists.

    Called on startup before any mode's `init`. Mode-specific schema is
    created by each mode's `init`, not here.
    """
    global _pool
    _pool = await asyncpg.create_pool(_database_url(), min_size=1, max_size=10, init=_init_conn)
    async with _pool.acquire() as conn:
        await conn.execute(_SENTINEL_SCHEMA)
    logger.info("datastore connected")


async def close() -> None:
    """Close the connection pool. Called on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def require_pool() -> asyncpg.Pool:
    """Return the live pool, or raise 503 if the backend is not connected."""
    if _pool is None:
        raise fastapi.HTTPException(status_code=503, detail="datastore not connected")
    return _pool


async def register_sentinel(
    pool: asyncpg.Pool,
    mode: str,
    shape: dict[str, typing.Any],
    note: str,
) -> None:
    """Upsert a mode's sentinel row. Idempotent, called from each mode's init."""
    await pool.execute(
        "INSERT INTO sentinels (mode, shape, note) VALUES ($1, $2, $3) "
        "ON CONFLICT (mode) DO UPDATE SET shape = EXCLUDED.shape, note = EXCLUDED.note",
        mode,
        shape,
        note,
    )


async def list_sentinels(pool: asyncpg.Pool) -> list[dict[str, typing.Any]]:
    """Return every registered sentinel, mode-ordered."""
    records = await pool.fetch("SELECT mode, shape, note, created_at FROM sentinels ORDER BY mode")
    return [
        {
            "mode": r["mode"],
            "shape": r["shape"],
            "note": r["note"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in records
    ]
