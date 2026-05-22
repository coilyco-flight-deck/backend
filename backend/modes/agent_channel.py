"""agent-channel mode - cross-host agent coordination channels.

Two tables. ``agent_channels`` is a registry of channels, each keyed by a
short 4-char dictatable id. ``agent_channel_events`` is the append-only
per-channel event log: coordination state, comms, status, and logs all land
here as events, newest-first on read.

``GET /agent-channel/{id}`` is a self-describing onboarding endpoint - an
agent handed only that URL learns what the channel is and how to take part.

Design: coilysiren/backend#77 (modes framework), coilysiren/agentic-os-kai#724,
coilysiren/agentic-os-kai#725 (move the channel off GitHub issues onto here).
"""

import secrets
import typing

import asyncpg
import fastapi
import pydantic
import yaml

from .. import datastore

MODE_NAME = "agent-channel"

router = fastapi.APIRouter(
    tags=["agent-channel"],
    dependencies=[fastapi.Depends(datastore.require_token)],
)

# Tailnet-internal base. The backend answers as host `api` via its ts sidecar.
_BASE_URL = "http://api"

# 4-char dictatable ids. Alphabet per agentic-os docs/dictatable-id-alphabet.md.
# 28^4 = 614k channels; channels are pruned, this is never close to full.
_ID_ALPHABET = "ABCDEFGHJKMPQRSTUVWXYZ456789"
_ID_LEN = 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_channels (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS agent_channel_events (
    id BIGSERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES agent_channels(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_channel_events_chan_created_idx
    ON agent_channel_events (channel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_channel_events_chan_kind_idx
    ON agent_channel_events (channel_id, kind, created_at DESC);
"""

_SENTINEL: dict[str, typing.Any] = {
    "shape": {
        "channel_id": "ABCD",
        "kind": "state | comms | status | log",
        "author": "claude-<os>-<host>-<tag> (from `coily agent-name`)",
        "payload": {"any": "json"},
    },
    "note": "agent coordination channels: a registry of 4-char-id channels plus "
    "an append-only per-channel event log. GET /agent-channel/{id} self-describes.",
}

# Chatty onboarding prose. An agent handed only the channel URL reads this and
# knows how to take part - written cold-pickup-friendly on purpose.
_ONBOARDING = (
    "You have reached an Agent Channel: a coordination channel for autonomous "
    "agents working across different hosts. If you were handed only this URL, "
    "good - that is the design, everything you need is in this response.\n\n"
    "Model: a channel is an append-only event log. Each event has a `kind` "
    "(`state`, `comms`, `status`, `log`, or whatever the protocol adds), an "
    "`author` (your name from `coily agent-name`), and a free-form JSON "
    "`payload`. The channel's current coordination state is the newest event "
    "of kind `state`: it carries the handoff holder, the open concepts (units "
    "of work, each with a legible id), and the known agents.\n\n"
    "To take part: (1) read `state` and `recent_events` below. (2) Get your "
    "name with `coily agent-name`. (3) If you hold the handoff, act on your "
    "open concept with full local autonomy, then POST your result to kind "
    "`comms` and POST a new `state` event passing the handoff on. (4) Post to "
    "kind `status` on a cadence while you work - silence reads as a dead "
    "agent. Full protocol: PROTOCOL.md in coilysiren/agentic-os-kai under "
    "scripts/agent-channel/."
)


class ChannelCreate(pydantic.BaseModel):
    """Request body for POST /agent-channel."""

    title: str = pydantic.Field(default="", max_length=200)
    created_by: str = pydantic.Field(default="", max_length=128)


class EventCreate(pydantic.BaseModel):
    """Request body for POST /agent-channel/{id}/event."""

    kind: str = pydantic.Field(min_length=1, max_length=64)
    author: str = pydantic.Field(default="", max_length=128)
    payload: dict[str, typing.Any]


def _new_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LEN))


def _norm_id(raw: str) -> str:
    """Normalize a path id to canonical form, or 404 if it cannot be one."""
    cid = raw.strip().upper()
    if len(cid) != _ID_LEN or any(c not in _ID_ALPHABET for c in cid):
        raise fastapi.HTTPException(status_code=404, detail="no such channel")
    return cid


def _channel_url(cid: str) -> str:
    return f"{_BASE_URL}/agent-channel/{cid}"


async def init(pool: asyncpg.Pool) -> None:
    """Create the channel tables and register the sentinel."""
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA)
    await datastore.register_sentinel(pool, MODE_NAME, _SENTINEL["shape"], _SENTINEL["note"])


def _channel(record: asyncpg.Record) -> dict[str, typing.Any]:
    return {
        "id": record["id"],
        "title": record["title"],
        "created_by": record["created_by"],
        "created_at": record["created_at"].isoformat(),
        "closed_at": record["closed_at"].isoformat() if record["closed_at"] else None,
        "url": _channel_url(record["id"]),
    }


def _event(record: asyncpg.Record) -> dict[str, typing.Any]:
    return {
        "id": record["id"],
        "channel_id": record["channel_id"],
        "kind": record["kind"],
        "author": record["author"],
        "payload": record["payload"],
        "created_at": record["created_at"].isoformat(),
    }


async def _load_channel(pool: asyncpg.Pool, cid: str) -> asyncpg.Record:
    record = await pool.fetchrow("SELECT * FROM agent_channels WHERE id = $1", cid)
    if record is None:
        raise fastapi.HTTPException(status_code=404, detail="no such channel")
    return record


# --- content negotiation for the onboarding view ---------------------------

_FORMAT_ALIASES = {
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "markdown": "markdown",
    "md": "markdown",
}


def _pick_format(explicit: str | None, accept: str) -> str:
    """Choose json / yaml / markdown from a ?format= override or the Accept header."""
    if explicit:
        return _FORMAT_ALIASES.get(explicit.strip().lower(), "json")
    accept = accept.lower()
    if "yaml" in accept:
        return "yaml"
    if "markdown" in accept:
        return "markdown"
    return "json"


def _md_scalar(value: typing.Any) -> str:
    if value is None:
        return "_(none)_"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).replace("\n", " ").strip()


def _md_lines(value: typing.Any, indent: int = 0) -> list[str]:
    """Render arbitrary JSON-ish data as an indented markdown bullet list."""
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, val in value.items():
            if isinstance(val, (dict, list)) and val:
                lines.append(f"{pad}- **{key}**:")
                lines.extend(_md_lines(val, indent + 1))
            else:
                lines.append(f"{pad}- **{key}**: {_md_scalar(val)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}-")
                lines.extend(_md_lines(item, indent + 1))
            else:
                lines.append(f"{pad}- {_md_scalar(item)}")
    else:
        lines.append(f"{pad}- {_md_scalar(value)}")
    return lines


def _channel_markdown(data: dict[str, typing.Any]) -> str:
    """Render the onboarding view as a human-readable markdown document."""
    ch = data["channel"]
    out: list[str] = [f"# Agent Channel {ch['id']}", ""]
    out.append(f"**{ch['title']}**" if ch.get("title") else "_(untitled channel)_")
    out += [
        "",
        f"- created by `{ch.get('created_by') or '(unknown)'}`",
        f"- created at {ch['created_at']}",
        f"- status: {'closed at ' + ch['closed_at'] if ch.get('closed_at') else 'open'}",
        f"- url: {ch['url']}",
        "",
        "## Onboarding",
        "",
        str(data.get("onboarding", "")),
        "",
        "## How to take part",
        "",
    ]
    out += _md_lines(data.get("participate", {}))
    out += ["", "## Charter", ""]
    spec = data.get("spec")
    out += _md_lines(spec) if spec else ["_No spec event yet._"]
    out += ["", "## Current state", ""]
    state = data.get("state")
    out += _md_lines(state) if state else ["_No state event yet._"]
    out += ["", "## Recent events", ""]
    events = data.get("recent_events") or []
    if not events:
        out.append("_No events yet._")
    for ev in events:
        author = ev.get("author") or "(no author)"
        out.append(f"### #{ev['id']} - {ev['kind']} - {author} - {ev['created_at']}")
        out += _md_lines(ev.get("payload", {}))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


@router.post("/agent-channel")
async def create_channel(body: ChannelCreate) -> dict[str, typing.Any]:
    """Create a channel with a fresh 4-char id. Returns the channel and its URL."""
    pool = datastore.require_pool()
    for _ in range(20):
        try:
            record = await pool.fetchrow(
                "INSERT INTO agent_channels (id, title, created_by) "
                "VALUES ($1, $2, $3) RETURNING *",
                _new_id(),
                body.title,
                body.created_by,
            )
            return _channel(record)
        except asyncpg.UniqueViolationError:
            continue
    raise fastapi.HTTPException(status_code=500, detail="could not allocate a channel id")


@router.get("/agent-channel")
async def list_channels(
    limit: int = 50, include_closed: bool = True
) -> list[dict[str, typing.Any]]:
    """List channels, newest first. Set include_closed=false to hide closed ones."""
    limit = max(1, min(limit, 500))
    pool = datastore.require_pool()
    if include_closed:
        records = await pool.fetch(
            "SELECT * FROM agent_channels ORDER BY created_at DESC LIMIT $1", limit
        )
    else:
        records = await pool.fetch(
            "SELECT * FROM agent_channels WHERE closed_at IS NULL "
            "ORDER BY created_at DESC LIMIT $1",
            limit,
        )
    return [_channel(r) for r in records]


@router.get("/agent-channel/{channel_id}", response_model=None)
async def get_channel(
    channel_id: str,
    request: fastapi.Request,
    format: str | None = None,
) -> fastapi.Response | dict[str, typing.Any]:
    """Self-describing onboarding view: prose, channel meta, latest state, recent events.

    Content-negotiates the response: JSON by default, YAML for an `application/yaml`
    Accept header, Markdown for `text/markdown`. A `?format=json|yaml|markdown` query
    param overrides the Accept header.
    """
    cid = _norm_id(channel_id)
    pool = datastore.require_pool()
    channel = await _load_channel(pool, cid)
    state = await pool.fetchrow(
        "SELECT * FROM agent_channel_events WHERE channel_id = $1 AND kind = 'state' "
        "ORDER BY created_at DESC LIMIT 1",
        cid,
    )
    spec = await pool.fetchrow(
        "SELECT * FROM agent_channel_events WHERE channel_id = $1 AND kind = 'spec' "
        "ORDER BY created_at DESC LIMIT 1",
        cid,
    )
    recent = await pool.fetch(
        "SELECT * FROM agent_channel_events WHERE channel_id = $1 "
        "ORDER BY created_at DESC LIMIT 20",
        cid,
    )
    data: dict[str, typing.Any] = {
        "channel": _channel(channel),
        "onboarding": _ONBOARDING,
        "participate": {
            "read_this": f"GET {_channel_url(cid)}",
            "read_spec": f"GET {_channel_url(cid)}/spec",
            "read_state": f"GET {_channel_url(cid)}/state",
            "read_events": f"GET {_channel_url(cid)}/events?kind=<kind>&limit=<n>",
            "append_event": f"POST {_channel_url(cid)}/event "
            '{"kind": "...", "author": "...", "payload": {...}}',
            "formats": f"GET {_channel_url(cid)}?format=json|yaml|markdown "
            "(or send a matching Accept header)",
            "auth": "Authorization: Bearer <token> - from SSM /coilysiren/backend/datastore-token",
            "your_name": "coily agent-name",
        },
        "spec": _event(spec)["payload"] if spec else None,
        "state": _event(state)["payload"] if state else None,
        "recent_events": [_event(r) for r in recent],
    }
    chosen = _pick_format(format, request.headers.get("accept", ""))
    if chosen == "yaml":
        return fastapi.Response(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            media_type="application/yaml",
        )
    if chosen == "markdown":
        return fastapi.Response(_channel_markdown(data), media_type="text/markdown")
    return data


@router.get("/agent-channel/{channel_id}/state")
async def get_state(channel_id: str) -> dict[str, typing.Any]:
    """Return the newest `state` event's payload, or 404 if the channel has none yet."""
    cid = _norm_id(channel_id)
    pool = datastore.require_pool()
    await _load_channel(pool, cid)
    record = await pool.fetchrow(
        "SELECT * FROM agent_channel_events WHERE channel_id = $1 AND kind = 'state' "
        "ORDER BY created_at DESC LIMIT 1",
        cid,
    )
    if record is None:
        raise fastapi.HTTPException(status_code=404, detail="channel has no state event yet")
    return _event(record)["payload"]


@router.get("/agent-channel/{channel_id}/spec")
async def get_spec(channel_id: str) -> dict[str, typing.Any]:
    """Return the newest `spec` event's payload (the channel charter), or 404."""
    cid = _norm_id(channel_id)
    pool = datastore.require_pool()
    await _load_channel(pool, cid)
    record = await pool.fetchrow(
        "SELECT * FROM agent_channel_events WHERE channel_id = $1 AND kind = 'spec' "
        "ORDER BY created_at DESC LIMIT 1",
        cid,
    )
    if record is None:
        raise fastapi.HTTPException(status_code=404, detail="channel has no spec event yet")
    return _event(record)["payload"]


@router.get("/agent-channel/{channel_id}/events")
async def list_events(
    channel_id: str,
    kind: str | None = None,
    limit: int = 50,
) -> list[dict[str, typing.Any]]:
    """List a channel's events, newest first. Optional `kind` filter. Luca polls this."""
    cid = _norm_id(channel_id)
    limit = max(1, min(limit, 500))
    pool = datastore.require_pool()
    await _load_channel(pool, cid)
    if kind is None:
        records = await pool.fetch(
            "SELECT * FROM agent_channel_events WHERE channel_id = $1 "
            "ORDER BY created_at DESC LIMIT $2",
            cid,
            limit,
        )
    else:
        records = await pool.fetch(
            "SELECT * FROM agent_channel_events WHERE channel_id = $1 AND kind = $2 "
            "ORDER BY created_at DESC LIMIT $3",
            cid,
            kind,
            limit,
        )
    return [_event(r) for r in records]


@router.post("/agent-channel/{channel_id}/event")
async def append_event(channel_id: str, body: EventCreate) -> dict[str, typing.Any]:
    """Append an event. State, comms, status, and logs all land here."""
    cid = _norm_id(channel_id)
    pool = datastore.require_pool()
    await _load_channel(pool, cid)
    record = await pool.fetchrow(
        "INSERT INTO agent_channel_events (channel_id, kind, author, payload) "
        "VALUES ($1, $2, $3, $4) RETURNING *",
        cid,
        body.kind,
        body.author,
        body.payload,
    )
    return _event(record)


@router.post("/agent-channel/{channel_id}/close")
async def close_channel(channel_id: str) -> dict[str, typing.Any]:
    """Mark a channel closed. Events stay readable; this just stamps closed_at."""
    cid = _norm_id(channel_id)
    pool = datastore.require_pool()
    await _load_channel(pool, cid)
    record = await pool.fetchrow(
        "UPDATE agent_channels SET closed_at = now() WHERE id = $1 RETURNING *", cid
    )
    return _channel(record)
