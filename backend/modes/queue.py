"""queue mode - SKIP LOCKED work queue.

A ``queue_jobs`` table backs an enqueue / claim / ack work queue. Claims use
``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent workers never hand out the
same job. ``visible_at`` carries both enqueue delay and the visibility timeout
after a claim. No LISTEN/NOTIFY in v1 - workers poll. Every route is authed.

Design: coilysiren/backend#77.
"""

import typing

import asyncpg
import fastapi
import pydantic

from .. import datastore

MODE_NAME = "queue"

router = fastapi.APIRouter(dependencies=[fastapi.Depends(datastore.require_token)])

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_jobs (
    id BIGSERIAL PRIMARY KEY,
    namespace TEXT NOT NULL,
    payload JSONB NOT NULL,
    visible_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS queue_jobs_ns_visible_idx
    ON queue_jobs (namespace, visible_at);
"""

_SENTINEL: dict[str, typing.Any] = {
    "shape": {
        "namespace": "example",
        "payload": {"any": "json"},
        "delay_seconds": 0,
        "visibility_timeout_seconds": 30,
    },
    "note": "SELECT FOR UPDATE SKIP LOCKED work queue; enqueue then claim then "
    "ack (delete). visible_at carries enqueue delay and post-claim visibility timeout.",
}


class EnqueueBody(pydantic.BaseModel):
    """Request body for POST /queue/{namespace}."""

    payload: dict[str, typing.Any]
    delay_seconds: int = pydantic.Field(default=0, ge=0, le=86_400)


class ClaimBody(pydantic.BaseModel):
    """Request body for POST /queue/{namespace}/claim."""

    visibility_timeout_seconds: int = pydantic.Field(default=30, ge=1, le=86_400)


async def init(pool: asyncpg.Pool) -> None:
    """Create the queue_jobs table and register the sentinel."""
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA)
    await datastore.register_sentinel(pool, MODE_NAME, _SENTINEL["shape"], _SENTINEL["note"])


def _job(record: asyncpg.Record) -> dict[str, typing.Any]:
    return {
        "id": record["id"],
        "namespace": record["namespace"],
        "payload": record["payload"],
        "visible_at": record["visible_at"].isoformat(),
        "claimed_at": record["claimed_at"].isoformat() if record["claimed_at"] else None,
        "created_at": record["created_at"].isoformat(),
    }


@router.post("/queue/{namespace}")
async def enqueue(namespace: str, body: EnqueueBody) -> dict[str, typing.Any]:
    """Enqueue a job. `delay_seconds` defers when it first becomes claimable."""
    pool = datastore.require_pool()
    record = await pool.fetchrow(
        "INSERT INTO queue_jobs (namespace, payload, visible_at) "
        "VALUES ($1, $2, now() + make_interval(secs => $3)) RETURNING *",
        namespace,
        body.payload,
        body.delay_seconds,
    )
    return _job(record)


@router.post("/queue/{namespace}/claim", response_model=None)
async def claim(namespace: str, body: ClaimBody) -> fastapi.Response | dict[str, typing.Any]:
    """Claim the oldest visible job. 204 with no body when the queue is empty.

    SKIP LOCKED means concurrent claimers never collide on the same row. The
    claimed job's `visible_at` is pushed out by the visibility timeout, so it
    reappears for re-claim if the worker dies before acking.
    """
    pool = datastore.require_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            record = await conn.fetchrow(
                "SELECT * FROM queue_jobs "
                "WHERE namespace = $1 AND visible_at <= now() "
                "ORDER BY visible_at "
                "FOR UPDATE SKIP LOCKED LIMIT 1",
                namespace,
            )
            if record is None:
                return fastapi.Response(status_code=204)
            updated = await conn.fetchrow(
                "UPDATE queue_jobs "
                "SET visible_at = now() + make_interval(secs => $2), claimed_at = now() "
                "WHERE id = $1 RETURNING *",
                record["id"],
                body.visibility_timeout_seconds,
            )
    return _job(updated)


@router.delete("/queue/{namespace}/{job_id}")
async def ack(namespace: str, job_id: int) -> dict[str, int]:
    """Ack a job by deleting it. Returns the row count removed (0 if already gone)."""
    pool = datastore.require_pool()
    result = await pool.execute(
        "DELETE FROM queue_jobs WHERE namespace = $1 AND id = $2", namespace, job_id
    )
    return {"deleted": int(result.split()[-1])}
