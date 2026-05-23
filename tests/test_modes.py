"""Tests for the modes framework.

The pure tests run anywhere - identifier and type validation, body model
validation, router registration. DB-integration tests are gated behind
BACKEND_TEST_DATABASE_URL like tests/test_datastore.py.
"""

import os

import fastapi
import pydantic
import pytest

from backend import modes
from backend.modes import agent_channel, document, file, health, queue, sql

# --- router registration ---------------------------------------------------


def test_all_modes_expose_router_and_init():
    for mode in modes.ALL_MODES:
        assert isinstance(mode.router, fastapi.APIRouter)
        assert callable(mode.init)
        assert isinstance(mode.MODE_NAME, str) and mode.MODE_NAME


def test_mode_names_match_modules():
    assert modes.MODE_NAMES == ["health", "document", "queue", "sql", "file", "agent-channel"]


def test_main_mounts_every_mode():
    from backend import main

    paths = {route.path for route in main.app.routes}
    # One representative path per mode.
    assert "/health" in paths
    assert "/document" in paths
    assert "/sql/tables" in paths
    assert "/files/temp" in paths
    assert "/agent-channel" in paths
    assert any(p.startswith("/queue/") for p in paths)


def test_mcp_endpoint_mounted():
    # The MCP server lives on its own carrier app, off the main middleware stack.
    from backend import main

    carrier_paths = {getattr(r, "path", "") for r in main._mcp_carrier.routes}
    assert any(p.startswith("/mcp") for p in carrier_paths)


def test_health_route_is_unauthed():
    # /health carries no dependency; every other mode router does.
    assert health.router.dependencies == []
    for mode in (document, queue, sql, file, agent_channel):
        assert len(mode.router.dependencies) == 1


# --- sql identifier validation (security-critical) -------------------------


@pytest.mark.parametrize(
    "name",
    ["t", "table1", "my_table", "a" * 63, "snake_case_99"],
)
def test_sql_valid_identifiers(name):
    assert sql._valid_ident(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",
        "1table",  # leading digit
        "Table",  # uppercase
        "my-table",  # hyphen
        "my table",  # space
        "a" * 64,  # too long
        "drop;",  # semicolon
        "t)--",  # sql metacharacters
        'tab"le',
        "tab'le",
        "_leading",  # leading underscore
    ],
)
def test_sql_invalid_identifiers(name):
    assert sql._valid_ident(name) is False


def test_sql_injection_attempt_rejected():
    bad = sql.TableCreate(
        name="users); DROP TABLE sentinels;--",
        columns=[{"name": "x", "type": "text"}],
    )
    with pytest.raises(fastapi.HTTPException) as exc:
        sql._validated_columns(bad)
    assert exc.value.status_code == 400


def test_sql_type_allowlist_accepts_known():
    names = "abcdefgh"
    spec = sql.TableCreate(
        name="goodtable",
        columns=[{"name": n, "type": t} for n, t in zip(names, sql._TYPE_ALLOWLIST, strict=False)],
    )
    cols = sql._validated_columns(spec)
    assert len(cols) == len(sql._TYPE_ALLOWLIST)
    # Every emitted pg type is concrete, not the user-facing alias.
    assert all(pg in sql._TYPE_ALLOWLIST.values() for _, pg in cols)


def test_sql_type_allowlist_rejects_unknown():
    spec = sql.TableCreate(name="goodtable", columns=[{"name": "x", "type": "varchar"}])
    with pytest.raises(fastapi.HTTPException) as exc:
        sql._validated_columns(spec)
    assert exc.value.status_code == 400
    assert "varchar" in exc.value.detail


def test_sql_rejects_bad_column_name():
    spec = sql.TableCreate(name="goodtable", columns=[{"name": "col-1", "type": "text"}])
    with pytest.raises(fastapi.HTTPException) as exc:
        sql._validated_columns(spec)
    assert exc.value.status_code == 400


def test_sql_rejects_reserved_column_name():
    for reserved in ("id", "created_at"):
        spec = sql.TableCreate(name="goodtable", columns=[{"name": reserved, "type": "text"}])
        with pytest.raises(fastapi.HTTPException) as exc:
            sql._validated_columns(spec)
        assert exc.value.status_code == 400


def test_sql_rejects_duplicate_columns():
    spec = sql.TableCreate(
        name="goodtable",
        columns=[{"name": "dup", "type": "text"}, {"name": "dup", "type": "int"}],
    )
    with pytest.raises(fastapi.HTTPException) as exc:
        sql._validated_columns(spec)
    assert exc.value.status_code == 400


# --- queue claim / enqueue body semantics ----------------------------------


def test_queue_enqueue_default_delay_is_zero():
    body = queue.EnqueueBody(payload={"task": "x"})
    assert body.delay_seconds == 0


def test_queue_enqueue_rejects_negative_delay():
    with pytest.raises(pydantic.ValidationError):
        queue.EnqueueBody(payload={}, delay_seconds=-1)


def test_queue_claim_default_visibility_timeout():
    body = queue.ClaimBody()
    assert body.visibility_timeout_seconds == 30


def test_queue_claim_rejects_zero_timeout():
    with pytest.raises(pydantic.ValidationError):
        queue.ClaimBody(visibility_timeout_seconds=0)


# --- document body validation ----------------------------------------------


def test_document_create_requires_namespace_and_key():
    with pytest.raises(pydantic.ValidationError):
        document.DocumentCreate(namespace="", key="k", payload={})
    with pytest.raises(pydantic.ValidationError):
        document.DocumentCreate(namespace="ns", key="", payload={})
    ok = document.DocumentCreate(namespace="ns", key="k", payload={"a": 1})
    assert ok.payload == {"a": 1}


# --- agent-channel mount shape ---------------------------------------------
# Detailed router + ids + models + onboarding tests live in
# coilysiren/otel-a2a-relay's channels/tests/. Backend only validates that
# the shim wires the package into this app.


def test_agent_channel_mode_constants_match_package():
    from otel_a2a_relay_channels import MODE_NAME as PKG_MODE_NAME

    assert agent_channel.MODE_NAME == PKG_MODE_NAME == "agent-channel"


def test_agent_channel_base_url_is_tailnet():
    assert agent_channel._BASE_URL == "http://api"


# --- file mode temp dir ----------------------------------------------------


def test_file_temp_dir_default(monkeypatch):
    monkeypatch.delenv("FILE_TEMP_DIR", raising=False)
    assert file._temp_dir() == "/data/temp"


def test_file_temp_dir_override(monkeypatch):
    monkeypatch.setenv("FILE_TEMP_DIR", "/tmp/custom")
    assert file._temp_dir() == "/tmp/custom"


# --- DB-integration: sentinel registration round-trip ----------------------


@pytest.mark.skipif(
    not os.getenv("BACKEND_TEST_DATABASE_URL"),
    reason="set BACKEND_TEST_DATABASE_URL to run the Postgres mode-init round-trip",
)
@pytest.mark.asyncio
async def test_mode_init_registers_sentinels(monkeypatch):
    from backend import datastore

    monkeypatch.setenv("DATABASE_URL", os.environ["BACKEND_TEST_DATABASE_URL"])
    await datastore.connect()
    try:
        pool = datastore.require_pool()
        for mode in modes.ALL_MODES:
            await mode.init(pool)
        registered = {s["mode"] for s in await datastore.list_sentinels(pool)}
        assert set(modes.MODE_NAMES).issubset(registered)
    finally:
        await datastore.close()
