"""document mode - jsonb document store.

An append-only ``documents`` table: small JSON payloads keyed by
``(namespace, key)``. Reads return newest-first. Every route is authed.

Design: coilysiren/backend#65, coilysiren/backend#77.
"""

import typing

import asyncpg
import fastapi
import pydantic

from .. import datastore

MODE_NAME = "document"

router = fastapi.APIRouter(dependencies=[fastapi.Depends(datastore.require_token)])

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_ns_key_created_idx
    ON documents (namespace, key, created_at DESC);
"""

_SENTINEL: dict[str, typing.Any] = {
    "shape": {"namespace": "example", "key": "example", "payload": {"any": "json"}},
    "note": "append-only jsonb document store; reads return newest-first per (namespace, key).",
}


class DocumentCreate(pydantic.BaseModel):
    """Request body for POST /document."""

    namespace: str = pydantic.Field(min_length=1, max_length=128)
    key: str = pydantic.Field(min_length=1, max_length=256)
    payload: dict[str, typing.Any]


async def init(pool: asyncpg.Pool) -> None:
    """Create the documents table and drop the dead `items` table."""
    async with pool.acquire() as conn:
        # The old empty `items` table from #65 is superseded by `documents`.
        await conn.execute("DROP TABLE IF EXISTS items")
        await conn.execute(_SCHEMA)
    await datastore.register_sentinel(pool, MODE_NAME, _SENTINEL["shape"], _SENTINEL["note"])


def _row(record: asyncpg.Record) -> dict[str, typing.Any]:
    return {
        "id": record["id"],
        "namespace": record["namespace"],
        "key": record["key"],
        "payload": record["payload"],
        "created_at": record["created_at"].isoformat(),
    }


@router.post("/document")
async def create_document(body: DocumentCreate) -> dict[str, typing.Any]:
    """Append a document. Rows are append-only; reads return the newest per key."""
    pool = datastore.require_pool()
    record = await pool.fetchrow(
        "INSERT INTO documents (namespace, key, payload) VALUES ($1, $2, $3) RETURNING *",
        body.namespace,
        body.key,
        body.payload,
    )
    return _row(record)


@router.get("/document/{namespace}")
async def list_documents(
    namespace: str,
    key: str | None = None,
    limit: int = 50,
) -> list[dict[str, typing.Any]]:
    """List documents in a namespace, newest first. Optional `key` filter."""
    limit = max(1, min(limit, 500))
    pool = datastore.require_pool()
    if key is None:
        records = await pool.fetch(
            "SELECT * FROM documents WHERE namespace = $1 ORDER BY created_at DESC LIMIT $2",
            namespace,
            limit,
        )
    else:
        records = await pool.fetch(
            "SELECT * FROM documents WHERE namespace = $1 AND key = $2 "
            "ORDER BY created_at DESC LIMIT $3",
            namespace,
            key,
            limit,
        )
    return [_row(r) for r in records]


@router.get("/document/{namespace}/{key}")
async def get_document(namespace: str, key: str) -> dict[str, typing.Any]:
    """Return the newest document for (namespace, key), or 404."""
    pool = datastore.require_pool()
    record = await pool.fetchrow(
        "SELECT * FROM documents WHERE namespace = $1 AND key = $2 "
        "ORDER BY created_at DESC LIMIT 1",
        namespace,
        key,
    )
    if record is None:
        raise fastapi.HTTPException(status_code=404, detail="document not found")
    return _row(record)


@router.delete("/document/{namespace}/{key}")
async def delete_documents(namespace: str, key: str) -> dict[str, int]:
    """Delete every document for (namespace, key). Returns the row count removed."""
    pool = datastore.require_pool()
    result = await pool.execute(
        "DELETE FROM documents WHERE namespace = $1 AND key = $2", namespace, key
    )
    # asyncpg returns a command tag like "DELETE 3".
    return {"deleted": int(result.split()[-1])}
