"""Ambient personal CRUD datastore.

A single generic `items(namespace, key, payload jsonb, created_at)` table in
Postgres. Schemaless document storage via `jsonb` plus real queries, one engine
to run. Rows are append-only; reads return the newest row per (namespace, key).

Design: coilysiren/backend#65, coilysiren/agentic-os-kai#657.
"""

import json
import os
import secrets
import typing

import asyncpg
import fastapi
import fastapi.security
import pydantic
import structlog

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS items_ns_key_created_idx
    ON items (namespace, key, created_at DESC);
"""

_bearer = fastapi.security.HTTPBearer(auto_error=False)


class ItemCreate(pydantic.BaseModel):
    """Request body for POST /items."""

    namespace: str = pydantic.Field(min_length=1, max_length=128)
    key: str = pydantic.Field(min_length=1, max_length=256)
    payload: dict[str, typing.Any]


def require_token(
    creds: fastapi.security.HTTPAuthorizationCredentials | None = fastapi.Depends(_bearer),
) -> None:
    """Validate the `Authorization: Bearer <token>` header against DATASTORE_TOKEN.

    Fails closed: if no token is configured the route is unavailable rather
    than open. The datastore holds personal data, so reads are authed too.
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
    """Open the connection pool and ensure the schema exists. Called on startup."""
    global _pool
    _pool = await asyncpg.create_pool(_database_url(), min_size=1, max_size=10, init=_init_conn)
    async with _pool.acquire() as conn:
        await conn.execute(_SCHEMA)
    logger.info("datastore connected")


async def close() -> None:
    """Close the connection pool. Called on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _require_pool() -> asyncpg.Pool:
    if _pool is None:
        raise fastapi.HTTPException(status_code=503, detail="datastore not connected")
    return _pool


def _row(record: asyncpg.Record) -> dict[str, typing.Any]:
    return {
        "id": record["id"],
        "namespace": record["namespace"],
        "key": record["key"],
        "payload": record["payload"],
        "created_at": record["created_at"].isoformat(),
    }


async def create_item(
    namespace: str, key: str, payload: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    async with _require_pool().acquire() as conn:
        record = await conn.fetchrow(
            "INSERT INTO items (namespace, key, payload) VALUES ($1, $2, $3) RETURNING *",
            namespace,
            key,
            payload,
        )
    return _row(record)


async def list_items(namespace: str, key: str | None, limit: int) -> list[dict[str, typing.Any]]:
    limit = max(1, min(limit, 500))
    async with _require_pool().acquire() as conn:
        if key is None:
            records = await conn.fetch(
                "SELECT * FROM items WHERE namespace = $1 ORDER BY created_at DESC LIMIT $2",
                namespace,
                limit,
            )
        else:
            records = await conn.fetch(
                "SELECT * FROM items WHERE namespace = $1 AND key = $2 "
                "ORDER BY created_at DESC LIMIT $3",
                namespace,
                key,
                limit,
            )
    return [_row(r) for r in records]


async def get_latest_item(namespace: str, key: str) -> dict[str, typing.Any] | None:
    async with _require_pool().acquire() as conn:
        record = await conn.fetchrow(
            "SELECT * FROM items WHERE namespace = $1 AND key = $2 "
            "ORDER BY created_at DESC LIMIT 1",
            namespace,
            key,
        )
    return _row(record) if record is not None else None


async def delete_items(namespace: str, key: str) -> int:
    async with _require_pool().acquire() as conn:
        result = await conn.execute(
            "DELETE FROM items WHERE namespace = $1 AND key = $2", namespace, key
        )
    # asyncpg returns a command tag like "DELETE 3".
    return int(result.split()[-1])
