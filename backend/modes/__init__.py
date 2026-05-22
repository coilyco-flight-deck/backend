"""Modes: one module per data-accessibility mode.

Each mode exposes a FastAPI ``router`` (an ``APIRouter``) and an async
``init(pool)`` that creates its schema and registers its sentinel. ``main.py``
mounts every router; ``application.py``'s lifespan opens the pool then calls
each mode's ``init``.

Adding a mode is a router plus a sentinel record - nothing else.

Design: coilysiren/backend#77.
"""

from . import agent_channel, document, file, health, queue, sql

# Ordered: health first so its sentinel lands before anything reads it.
ALL_MODES = [health, document, queue, sql, file, agent_channel]

MODE_NAMES = [m.MODE_NAME for m in ALL_MODES]

__all__ = [
    "ALL_MODES",
    "MODE_NAMES",
    "agent_channel",
    "document",
    "file",
    "health",
    "queue",
    "sql",
]
