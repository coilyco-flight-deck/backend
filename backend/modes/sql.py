"""sql mode - generic relational mode.

Create a real typed Postgres table from a column spec, then CRUD its rows.
A ``sql_tables`` registry tracks every created table. This is the "dispatch a
new table type from mobile" surface.

Identifier validation is load-bearing. Table and column names are validated
against a strict regex and types against a closed allowlist before any
identifier is interpolated into DDL. Values always go through parameterized
placeholders. An unvalidated identifier must never reach a SQL string.

Every created table is namespaced as ``sql_<name>`` on the cluster.

Design: coilysiren/backend#77.
"""

import re
import typing

import asyncpg
import fastapi
import pydantic

from .. import datastore

MODE_NAME = "sql"

router = fastapi.APIRouter(dependencies=[fastapi.Depends(datastore.require_token)])

# 63-char identifier matches Postgres's NAMEDATALEN-1 cap.
# Leaves room for the sql_ prefix on the created table name.
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# Closed type allowlist. Anything outside this set is a 400. Mapped to the
# concrete Postgres type emitted into the CREATE TABLE DDL.
_TYPE_ALLOWLIST: dict[str, str] = {
    "text": "TEXT",
    "int": "INTEGER",
    "bigint": "BIGINT",
    "bool": "BOOLEAN",
    "timestamptz": "TIMESTAMPTZ",
    "jsonb": "JSONB",
    "numeric": "NUMERIC",
    "double": "DOUBLE PRECISION",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sql_tables (
    name TEXT PRIMARY KEY,
    columns JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_SENTINEL: dict[str, typing.Any] = {
    "shape": {
        "name": "example",
        "columns": [{"name": "title", "type": "text"}, {"name": "count", "type": "int"}],
    },
    "note": "generic relational mode; POST /sql/tables creates a real typed table "
    "sql_<name>, then CRUD rows. Identifier + type validation is security-critical.",
}


class ColumnSpec(pydantic.BaseModel):
    """One column in a create-table spec."""

    name: str
    type: str


class TableCreate(pydantic.BaseModel):
    """Request body for POST /sql/tables."""

    name: str
    columns: list[ColumnSpec] = pydantic.Field(min_length=1, max_length=64)


def _valid_ident(name: str) -> bool:
    """Return True if `name` is a safe SQL identifier under the strict regex."""
    return bool(_IDENT_RE.match(name))


def _validated_columns(spec: TableCreate) -> list[tuple[str, str]]:
    """Validate the table spec, returning (column_name, pg_type) pairs.

    Raises HTTPException(400) on any invalid identifier, unknown type, or
    duplicate column name. Callers must use this before emitting any DDL.
    """
    if not _valid_ident(spec.name):
        raise fastapi.HTTPException(status_code=400, detail=f"invalid table name: {spec.name!r}")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for col in spec.columns:
        if not _valid_ident(col.name):
            raise fastapi.HTTPException(
                status_code=400, detail=f"invalid column name: {col.name!r}"
            )
        if col.name in ("id", "created_at"):
            raise fastapi.HTTPException(
                status_code=400, detail=f"column name {col.name!r} is reserved"
            )
        if col.name in seen:
            raise fastapi.HTTPException(
                status_code=400, detail=f"duplicate column name: {col.name!r}"
            )
        pg_type = _TYPE_ALLOWLIST.get(col.type)
        if pg_type is None:
            raise fastapi.HTTPException(
                status_code=400, detail=f"unsupported column type: {col.type!r}"
            )
        seen.add(col.name)
        out.append((col.name, pg_type))
    return out


async def init(pool: asyncpg.Pool) -> None:
    """Create the sql_tables registry and register the sentinel."""
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA)
    await datastore.register_sentinel(pool, MODE_NAME, _SENTINEL["shape"], _SENTINEL["note"])


@router.post("/sql/tables")
async def create_table(body: TableCreate) -> dict[str, typing.Any]:
    """Create a real typed table `sql_<name>` and record it in the registry.

    Every identifier is validated before it reaches the DDL string. The 400
    rejections happen in `_validated_columns` before any SQL is built.
    """
    columns = _validated_columns(body)
    # Identifiers below are validated above; values are never interpolated.
    col_ddl = ", ".join(f"{name} {pg_type}" for name, pg_type in columns)
    table = f"sql_{body.name}"
    pool = datastore.require_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} ("
                "id BIGSERIAL PRIMARY KEY, "
                f"{col_ddl}, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            await conn.execute(
                "INSERT INTO sql_tables (name, columns) VALUES ($1, $2) "
                "ON CONFLICT (name) DO UPDATE SET columns = EXCLUDED.columns",
                body.name,
                [{"name": c.name, "type": c.type} for c in body.columns],
            )
    return {"name": body.name, "table": table, "columns": body.columns}


@router.get("/sql/tables")
async def list_tables() -> list[dict[str, typing.Any]]:
    """List the registry of created tables."""
    pool = datastore.require_pool()
    records = await pool.fetch("SELECT name, columns, created_at FROM sql_tables ORDER BY name")
    return [
        {
            "name": r["name"],
            "columns": r["columns"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in records
    ]


async def _registered_columns(pool: asyncpg.Pool, name: str) -> list[dict[str, str]]:
    """Return the registered column spec for `name`, or raise 404."""
    if not _valid_ident(name):
        raise fastapi.HTTPException(status_code=400, detail=f"invalid table name: {name!r}")
    row = await pool.fetchval("SELECT columns FROM sql_tables WHERE name = $1", name)
    if row is None:
        raise fastapi.HTTPException(status_code=404, detail=f"table not registered: {name!r}")
    return row


@router.post("/sql/tables/{name}/rows")
async def insert_row(name: str, body: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """Insert a row. Only registered columns are accepted; values are parameterized."""
    pool = datastore.require_pool()
    columns = await _registered_columns(pool, name)
    known = {c["name"] for c in columns}
    supplied = [c for c in known if c in body]
    if not supplied:
        raise fastapi.HTTPException(status_code=400, detail="no known columns supplied")
    unknown = set(body) - known
    if unknown:
        raise fastapi.HTTPException(status_code=400, detail=f"unknown columns: {sorted(unknown)}")
    # `supplied` is a subset of registry column names, each regex-validated at
    # create-table time. Values go through $N placeholders.
    col_list = ", ".join(supplied)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(supplied)))
    values = [body[c] for c in supplied]
    record = await pool.fetchrow(
        f"INSERT INTO sql_{name} ({col_list}) VALUES ({placeholders}) RETURNING *",
        *values,
    )
    return {k: _jsonable(v) for k, v in dict(record).items()}


@router.get("/sql/tables/{name}/rows")
async def list_rows(name: str, limit: int = 50) -> list[dict[str, typing.Any]]:
    """Select rows, newest first."""
    pool = datastore.require_pool()
    await _registered_columns(pool, name)  # validates `name` and 404s if unknown
    limit = max(1, min(limit, 500))
    records = await pool.fetch(f"SELECT * FROM sql_{name} ORDER BY created_at DESC LIMIT $1", limit)
    return [{k: _jsonable(v) for k, v in dict(r).items()} for r in records]


def _jsonable(value: typing.Any) -> typing.Any:
    """Coerce asyncpg row values into JSON-serializable form."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
