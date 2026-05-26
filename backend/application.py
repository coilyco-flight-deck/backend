import asyncio
import contextlib

import fastapi
import fastapi.middleware.cors as cors
import opentelemetry.trace as otel_trace
import requests.exceptions
import sentry_sdk
import slowapi
import slowapi.errors
import slowapi.util
import starlette.middleware.base as middleware
import starlette.requests
import starlette.responses
import structlog

from . import datastore
from . import telemetry as _telemetry

telemetry = _telemetry.Telemetry()
logger = structlog.get_logger()


class OpenTelemetryMiddleware(middleware.BaseHTTPMiddleware):
    """Middleware to handle OpenTelemetry tracing for incoming HTTP requests."""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(
        self,
        request: starlette.requests.Request,
        call_next: middleware.RequestResponseEndpoint,
    ) -> starlette.responses.Response:
        with telemetry.tracer.start_as_current_span("OpenTelemetryMiddleware") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.request.path", request.url.path)

            query_params = {}
            for key, value in request.query_params.items():
                span.set_attribute(f"http.request.query.{key}", value)
                query_params[key] = value

            path_params = {}
            for key, value in request.path_params.items():
                span.set_attribute(f"http.request.path.{key}", value)
                path_params[key] = value

            logger.info(
                "request starting",
                method=request.method,
                url=str(request.url),
                path=request.url.path,
                **query_params,
                **path_params,
            )
            response = await call_next(request)
            logger.info(
                "request finishing",
                status_code=response.status_code,
                method=request.method,
                url=str(request.url),
                path=request.url.path,
                **query_params,
                **path_params,
            )
            span.set_attribute("http.status_code", response.status_code)
            return response


class ErrorHandlingMiddleware(middleware.BaseHTTPMiddleware):
    """Middleware to handle exceptions and return JSON responses"""

    timeout: int

    def __init__(self, app, timeout: int):
        super().__init__(app)
        self.timeout = timeout

    def _capture_exception(self, span: otel_trace.Span, exc: Exception) -> None:
        sentry_sdk.capture_exception(exc)
        span.set_status(otel_trace.StatusCode.ERROR, str(exc))
        span.set_attribute("exception.type", type(exc).__name__)
        span.set_attribute("exception.message", str(exc))
        span.record_exception(exc)

    async def dispatch(
        self,
        request: starlette.requests.Request,
        call_next: middleware.RequestResponseEndpoint,
    ) -> starlette.responses.Response:
        with telemetry.tracer.start_as_current_span("ErrorHandlingMiddleware") as span:
            try:
                return await asyncio.wait_for(call_next(request), timeout=self.timeout)

            except requests.exceptions.HTTPError as exc:
                try:
                    message = exc.response.json()
                except requests.exceptions.JSONDecodeError:
                    message = exc.response.text
                logger.exception("HTTP error", exc=exc)
                return starlette.responses.JSONResponse(
                    {"detail": message}, status_code=exc.response.status_code
                )

            # handle any kind of timeout errors, note that we enforce the timeouts
            except TimeoutError as exc:
                self._capture_exception(span, exc)

                message = "request timed out"
                logger.error(message, exc=exc, status_code=408)
                return starlette.responses.JSONResponse({"detail": message}, status_code=408)

            # handle other exceptions that may occur during request processing
            except Exception as exc:
                self._capture_exception(span, exc)

                message = "internal server error"
                logger.error(message, exc=exc, status_code=500)
                return starlette.responses.JSONResponse(
                    {"detail": message, "error": str(exc)},
                    status_code=500,
                )


@contextlib.asynccontextmanager
async def _lifespan(_app: fastapi.FastAPI):
    """Open the Postgres pool, init every mode on startup, close on shutdown.

    Each mode's `init` creates its schema and upserts its sentinel. Done here
    so the modes package stays decoupled from the app object.
    """
    from . import modes

    await datastore.connect()
    pool = datastore.require_pool()
    for mode in modes.ALL_MODES:
        await mode.init(pool)
    yield
    await datastore.close()


def init() -> tuple[fastapi.FastAPI, slowapi.Limiter]:
    app = fastapi.FastAPI(lifespan=_lifespan)

    app.add_middleware(ErrorHandlingMiddleware, timeout=30)

    app.add_middleware(OpenTelemetryMiddleware)

    # CORS permissive: tailnet-internal service, no public ingress.
    app.add_middleware(cors.CORSMiddleware, allow_origins=["*"])

    # slowapi rate limiting. https://slowapi.readthedocs.io/en/latest/
    # pylint: disable=protected-access
    limiter = slowapi.Limiter(key_func=slowapi.util.get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(
        slowapi.errors.RateLimitExceeded,
        slowapi._rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )
    # pylint: enable=protected-access

    return app, limiter
