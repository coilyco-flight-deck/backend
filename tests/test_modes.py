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


# --- agent-channel id + body validation ------------------------------------


def test_agent_channel_new_id_shape():
    for _ in range(200):
        cid = agent_channel._new_id()
        assert len(cid) == agent_channel._ID_LEN
        assert all(c in agent_channel._ID_ALPHABET for c in cid)


def test_agent_channel_id_alphabet_is_unambiguous():
    # Dictatable: no I/L/O/0/1 to mishear.
    for bad in "ILO01":
        assert bad not in agent_channel._ID_ALPHABET


def test_agent_channel_norm_id_uppercases_valid():
    valid = agent_channel._new_id().lower()
    assert agent_channel._norm_id(valid) == valid.upper()
    assert agent_channel._norm_id(f"  {valid}  ") == valid.upper()


@pytest.mark.parametrize("bad", ["", "ABC", "ABCDE", "AB1D", "AB-D", "abci"])
def test_agent_channel_norm_id_rejects_malformed(bad):
    with pytest.raises(fastapi.HTTPException) as exc:
        agent_channel._norm_id(bad)
    assert exc.value.status_code == 404


def test_agent_channel_event_requires_kind():
    with pytest.raises(pydantic.ValidationError):
        agent_channel.EventCreate(kind="", author="a", payload={})
    ok = agent_channel.EventCreate(kind="state", author="claude-x", payload={"a": 1})
    assert ok.kind == "state"


def test_agent_channel_create_defaults_are_empty():
    body = agent_channel.ChannelCreate()
    assert body.title == "" and body.created_by == ""


def test_agent_channel_url_shape():
    assert agent_channel._channel_url("ABCD") == "http://api/agent-channel/ABCD"


def test_agent_channel_pick_format_explicit_overrides_accept():
    assert agent_channel._pick_format("yaml", "text/markdown") == "yaml"
    assert agent_channel._pick_format("md", "") == "markdown"
    assert agent_channel._pick_format("json", "application/yaml") == "json"
    assert agent_channel._pick_format("nonsense", "") == "json"


def test_agent_channel_pick_format_from_accept_header():
    assert agent_channel._pick_format(None, "application/yaml") == "yaml"
    assert agent_channel._pick_format(None, "text/markdown") == "markdown"
    assert agent_channel._pick_format(None, "application/json") == "json"
    assert agent_channel._pick_format(None, "") == "json"


def test_agent_channel_markdown_render():
    data = {
        "channel": {
            "id": "VHGC",
            "title": "Test channel",
            "created_by": "claude-x",
            "created_at": "2026-05-22T10:00:00+00:00",
            "closed_at": None,
            "url": "http://api/agent-channel/VHGC",
        },
        "onboarding": "welcome",
        "participate": {"read_this": "GET ..."},
        "spec": {"mission": "ship it", "rules": ["no docker for k3s"]},
        "state": {"mission": "do it", "concepts": [{"id": "k3s-health", "status": "proposed"}]},
        "recent_events": [
            {
                "id": 1,
                "kind": "state",
                "author": "claude-x",
                "created_at": "2026-05-22T10:00:00+00:00",
                "payload": {"a": 1},
            }
        ],
    }
    md = agent_channel._channel_markdown(data)
    assert md.startswith("# Agent Channel VHGC")
    assert "## Charter" in md
    assert "no docker for k3s" in md
    assert "## Current state" in md
    assert "k3s-health" in md
    assert "## Recent events" in md
    assert "#1 - state - claude-x" in md


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
