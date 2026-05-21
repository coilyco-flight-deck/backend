"""Tests for the ambient datastore auth and DSN logic.

The pure tests run anywhere. The CRUD round-trip is skipped unless
BACKEND_TEST_DATABASE_URL points at a throwaway Postgres.
"""

import os

import fastapi
import fastapi.security
import pytest

from backend import datastore


def _creds(token: str) -> fastapi.security.HTTPAuthorizationCredentials:
    return fastapi.security.HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_require_token_unconfigured(monkeypatch):
    monkeypatch.delenv("DATASTORE_TOKEN", raising=False)
    with pytest.raises(fastapi.HTTPException) as exc:
        datastore.require_token(_creds("anything"))
    assert exc.value.status_code == 503


def test_require_token_missing_header(monkeypatch):
    monkeypatch.setenv("DATASTORE_TOKEN", "secret")
    with pytest.raises(fastapi.HTTPException) as exc:
        datastore.require_token(None)
    assert exc.value.status_code == 401


def test_require_token_wrong(monkeypatch):
    monkeypatch.setenv("DATASTORE_TOKEN", "secret")
    with pytest.raises(fastapi.HTTPException) as exc:
        datastore.require_token(_creds("nope"))
    assert exc.value.status_code == 401


def test_require_token_ok(monkeypatch):
    monkeypatch.setenv("DATASTORE_TOKEN", "secret")
    assert datastore.require_token(_creds("secret")) is None


def test_database_url_from_parts(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "db.example")
    monkeypatch.setenv("PGUSER", "alice")
    monkeypatch.setenv("PGPASSWORD", "hunter2")
    monkeypatch.setenv("PGDATABASE", "store")
    monkeypatch.setenv("PGPORT", "6000")
    url = datastore._database_url()
    assert url.startswith("postgresql://")
    assert "alice" in url and "hunter2" in url
    assert "db.example:6000/store" in url


def test_database_url_prefers_full(monkeypatch):
    sentinel = "postgresql://" + "explicitly-set"
    monkeypatch.setenv("DATABASE_URL", sentinel)
    assert datastore._database_url() == sentinel


@pytest.mark.skipif(
    not os.getenv("BACKEND_TEST_DATABASE_URL"),
    reason="set BACKEND_TEST_DATABASE_URL to run the Postgres CRUD round-trip",
)
@pytest.mark.asyncio
async def test_crud_round_trip(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["BACKEND_TEST_DATABASE_URL"])
    await datastore.connect()
    try:
        ns, key = "pytest", "round-trip"
        await datastore.delete_items(ns, key)

        created = await datastore.create_item(ns, key, {"n": 1})
        assert created["payload"] == {"n": 1}

        await datastore.create_item(ns, key, {"n": 2})
        latest = await datastore.get_latest_item(ns, key)
        assert latest is not None and latest["payload"] == {"n": 2}

        listed = await datastore.list_items(ns, key, 50)
        assert len(listed) == 2

        assert await datastore.delete_items(ns, key) == 2
        assert await datastore.get_latest_item(ns, key) is None
    finally:
        await datastore.close()
