"""Entry point: build the app and mount every mode's router.

`backend` is a generic data-accessibility framework. Each mode under
`backend/modes/` owns a table and ships an `APIRouter` plus an `init`. This
module mounts all of them; `application.py`'s lifespan calls each `init`.

Design: coilysiren/backend#77.
"""

import dotenv
import fastapi
import opentelemetry.instrumentation.fastapi as otel_fastapi
import structlog
import structlog.processors
from fastapi_mcp import FastApiMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from . import application, modes

dotenv.load_dotenv()
(app, limiter) = application.init()

structlog.configure(
    processors=[
        structlog.processors.JSONRenderer(sort_keys=True),
    ]
)


class _MCPPassthrough:
    """Pure-ASGI middleware that diverts /mcp to a middleware-free carrier app.

    The MCP streamable-HTTP transport holds a stream open, which the main app's
    Starlette BaseHTTPMiddleware stack mangles into an empty response (backend#87).
    This routes /mcp straight to the carrier before that stack runs. Pure ASGI, so
    it does not break the stream the way BaseHTTPMiddleware does.
    """

    def __init__(self, app: ASGIApp, mcp_carrier: ASGIApp) -> None:
        self.app = app
        self.mcp_carrier = mcp_carrier

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/mcp" or path.startswith("/mcp/")):
            await self.mcp_carrier(scope, receive, send)
            return
        await self.app(scope, receive, send)


@app.get("/")
@limiter.limit("10/second")
async def root(request: fastapi.Request):
    return ["hello", "world"]


@app.get("/explode")
@app.get("/explode/")
async def trigger_error():
    """Force an exception. Smoke test for Sentry + the error middleware."""
    return 1 / 0


# Mount every mode's router. Each mode owns one table and a sentinel record;
# adding a mode is a new module under backend/modes/ plus an entry in its
# ALL_MODES list - nothing in this file changes.
for _mode in modes.ALL_MODES:
    app.include_router(_mode.router)

# agent-channel MCP tools on a middleware-free carrier app (backend#87).
_mcp_carrier = fastapi.FastAPI()
_mcp = FastApiMCP(
    app,
    name="agent-channel",
    description="Cross-host agent coordination channels - see PROTOCOL.md in agentic-os-kai.",
    include_tags=["agent-channel"],
)
_mcp.mount_http(router=_mcp_carrier)

otel_fastapi.FastAPIInstrumentor.instrument_app(app)

app.add_middleware(_MCPPassthrough, mcp_carrier=_mcp_carrier)
