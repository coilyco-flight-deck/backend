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

from . import application, modes

dotenv.load_dotenv()
(app, limiter) = application.init()

structlog.configure(
    processors=[
        structlog.processors.JSONRenderer(sort_keys=True),
    ]
)


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


otel_fastapi.FastAPIInstrumentor.instrument_app(app)
