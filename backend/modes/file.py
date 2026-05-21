"""file mode - temp-tier file storage, write-only.

``POST /files/temp`` accepts a raw request body and writes it to a uuid-named
file under ``FILE_TEMP_DIR`` (an ``emptyDir`` in the deployed Pod). There is no
read, list, or delete route by design - the temp tier is write-only in v1.
The directory is ephemeral, so anything written here is best-effort and gone
on Pod restart.

Design: coilysiren/backend#77.
"""

import json
import os
import typing
import uuid

import asyncpg
import fastapi

from .. import datastore

MODE_NAME = "file"

router = fastapi.APIRouter(dependencies=[fastapi.Depends(datastore.require_token)])

_SENTINEL: dict[str, typing.Any] = {
    "shape": {"id": "<uuid4>", "bytes": 0},
    "note": "temp-tier file storage, write-only; POST /files/temp writes a raw body "
    "to FILE_TEMP_DIR/<uuid4> on an ephemeral emptyDir. No read route by design.",
}


def _temp_dir() -> str:
    """Resolve the temp directory from FILE_TEMP_DIR, defaulting to /data/temp."""
    return os.getenv("FILE_TEMP_DIR", "/data/temp")


async def init(pool: asyncpg.Pool) -> None:
    """Create the temp dir, drop a self-describing .sentinel.json, register the sentinel."""
    temp_dir = _temp_dir()
    os.makedirs(temp_dir, exist_ok=True)
    sentinel_path = os.path.join(temp_dir, ".sentinel.json")
    with open(sentinel_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "mode": MODE_NAME,
                "format": "each file is a uuid4-named blob of a raw POST body",
                "note": "temp tier - ephemeral emptyDir, write-only, no rotation in v1",
            },
            handle,
        )
    await datastore.register_sentinel(pool, MODE_NAME, _SENTINEL["shape"], _SENTINEL["note"])


@router.post("/files/temp")
async def write_temp_file(
    request: fastapi.Request,
    name: str | None = None,
) -> dict[str, typing.Any]:
    """Write the raw request body to a uuid-named file. Returns its id and byte count.

    The optional `?name=` is a caller hint only; the stored filename is always
    a fresh uuid4 so callers cannot collide or path-traverse.
    """
    body = await request.body()
    file_id = str(uuid.uuid4())
    path = os.path.join(_temp_dir(), file_id)
    with open(path, "wb") as handle:
        handle.write(body)
    return {"id": file_id, "bytes": len(body), "name_hint": name}
