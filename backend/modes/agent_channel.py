"""agent-channel mode - thin shim over `otel-a2a-relay-channels`.

The canonical implementation (router, schema, models, onboarding view, OTel
span emission) lives in coilysiren/otel-a2a-relay's `channels/` workspace
package. This module wires backend's datastore (pool + bearer-auth) into
that package's `make_router(...)` factory, then re-exports the surface
`backend/modes/__init__.py` expects (`MODE_NAME`, `router`, `init`).

Move history: coilysiren/otel-a2a-relay#132 (the package), this issue
coilysiren/backend#90.
"""

import asyncpg
from otel_a2a_relay_channels import (
    MODE_NAME,
    SCHEMA,
    SENTINEL_NOTE,
    SENTINEL_SHAPE,
    make_router,
)

from .. import datastore

__all__ = ["MODE_NAME", "init", "router"]

# Tailnet-internal base. The backend answers as host `api` via its ts sidecar.
_BASE_URL = "http://api"

router = make_router(
    pool_provider=datastore.require_pool,
    auth_dependency=datastore.require_token,
    base_url=_BASE_URL,
)


async def init(pool: asyncpg.Pool) -> None:
    """Create the channel tables and register the sentinel."""
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
    await datastore.register_sentinel(pool, MODE_NAME, SENTINEL_SHAPE, SENTINEL_NOTE)
