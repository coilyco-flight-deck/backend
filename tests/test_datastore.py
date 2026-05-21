"""Tests for the shared datastore layer: auth, DSN, and sentinel registry.

The pure tests run anywhere. The DB round-trip is skipped unless
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


def test_require_pool_unconnected():
    # No pool open in a pure test process.
    datastore._pool = None
    with pytest.raises(fastapi.HTTPException) as exc:
        datastore.require_pool()
    assert exc.value.status_code == 503


@pytest.mark.skipif(
    not os.getenv("BACKEND_TEST_DATABASE_URL"),
    reason="set BACKEND_TEST_DATABASE_URL to run the Postgres sentinel round-trip",
)
@pytest.mark.asyncio
async def test_sentinel_round_trip(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["BACKEND_TEST_DATABASE_URL"])
    await datastore.connect()
    try:
        pool = datastore.require_pool()
        await datastore.register_sentinel(pool, "pytest-mode", {"field": "value"}, "test sentinel")
        sentinels = await datastore.list_sentinels(pool)
        match = [s for s in sentinels if s["mode"] == "pytest-mode"]
        assert len(match) == 1
        assert match[0]["shape"] == {"field": "value"}
        # Upsert is idempotent.
        await datastore.register_sentinel(
            pool, "pytest-mode", {"field": "updated"}, "test sentinel"
        )
        sentinels = await datastore.list_sentinels(pool)
        match = [s for s in sentinels if s["mode"] == "pytest-mode"]
        assert match[0]["shape"] == {"field": "updated"}
        await pool.execute("DELETE FROM sentinels WHERE mode = 'pytest-mode'")
    finally:
        await datastore.close()
