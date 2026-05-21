"""health mode - liveness probe and framework self-description.

``GET /health`` checks DB connectivity and returns the mounted modes plus
every registered sentinel. It is the only unauthed route in the framework:
a k8s liveness probe cannot carry a bearer token.

Design: coilysiren/backend#77.
"""

import typing

import fastapi

from .. import datastore

MODE_NAME = "health"

router = fastapi.APIRouter()

# This mode owns no table of its own. Its sentinel documents the /health
# response shape so the framework self-describes through the same channel.
_SENTINEL: dict[str, typing.Any] = {
    "shape": {"status": "ok", "db": "up", "modes": ["..."], "sentinels": ["..."]},
    "note": "health mode owns no table; GET /health reports DB connectivity, "
    "mounted modes, and every mode's sentinel. Unauthed - it is the liveness probe.",
}


async def init(pool: typing.Any) -> None:
    """Register the health sentinel. No mode-owned schema."""
    await datastore.register_sentinel(pool, MODE_NAME, _SENTINEL["shape"], _SENTINEL["note"])


@router.get("/health")
async def health() -> dict[str, typing.Any]:
    """Liveness probe. Reports DB connectivity, mounted modes, and sentinels.

    Intentionally unauthed. Returns 200 with ``db: "down"`` rather than an
    error when the pool is missing, so the probe distinguishes "process up,
    DB down" from "process down".
    """
    # Import here to avoid a circular import at module load.
    from . import MODE_NAMES

    db = "down"
    sentinels: list[dict[str, typing.Any]] = []
    try:
        pool = datastore.require_pool()
        row = await pool.fetchval("SELECT 1")
        if row == 1:
            db = "up"
        sentinels = await datastore.list_sentinels(pool)
    except Exception:
        db = "down"

    return {
        "status": "ok" if db == "up" else "degraded",
        "db": db,
        "modes": MODE_NAMES,
        "sentinels": sentinels,
    }
