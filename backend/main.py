import dotenv
import fastapi
import opentelemetry.instrumentation.fastapi as otel_fastapi
import structlog
import structlog.processors

from . import application, datastore

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


# Ambient personal CRUD datastore. A generic `items` table in Postgres holds
# small JSON documents keyed by (namespace, key). First consumer is the CI
# release pipeline writing build/deploy status that the Mac side polls.
# Design: coilysiren/backend#65, coilysiren/agentic-os-kai#657.


@app.post("/items")
@app.post("/items/")
@limiter.limit("20/second")
async def create_item(
    request: fastapi.Request,
    body: datastore.ItemCreate,
    _: None = fastapi.Depends(datastore.require_token),
):
    """Append a document. Rows are append-only; reads return the newest per key."""
    return await datastore.create_item(body.namespace, body.key, body.payload)


@app.get("/items/{namespace}")
@app.get("/items/{namespace}/")
@limiter.limit("20/second")
async def list_items(
    request: fastapi.Request,
    namespace: str,
    key: str | None = None,
    limit: int = 50,
    _: None = fastapi.Depends(datastore.require_token),
):
    """List documents in a namespace, newest first. Optional `key` filter."""
    return await datastore.list_items(namespace, key, limit)


@app.get("/items/{namespace}/{key}")
@app.get("/items/{namespace}/{key}/")
@limiter.limit("20/second")
async def get_item(
    request: fastapi.Request,
    namespace: str,
    key: str,
    _: None = fastapi.Depends(datastore.require_token),
):
    """Return the newest document for (namespace, key), or 404."""
    item = await datastore.get_latest_item(namespace, key)
    if item is None:
        raise fastapi.HTTPException(status_code=404, detail="item not found")
    return item


@app.delete("/items/{namespace}/{key}")
@app.delete("/items/{namespace}/{key}/")
@limiter.limit("20/second")
async def delete_item(
    request: fastapi.Request,
    namespace: str,
    key: str,
    _: None = fastapi.Depends(datastore.require_token),
):
    """Delete every document for (namespace, key). Returns the row count removed."""
    deleted = await datastore.delete_items(namespace, key)
    return {"deleted": deleted}


otel_fastapi.FastAPIInstrumentor.instrument_app(app)
