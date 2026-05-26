"""Verify Sentry error capture survives across the backend app.

Filed against coilysiren/backend#78. The app wires Sentry in
`backend/telemetry.py` and routes every exception through
`ErrorHandlingMiddleware._capture_exception` in `backend/application.py`.
These tests turn the issue's one-time manual smoke test into a permanent
regression check: a forced exception must reach the Sentry SDK.
"""

import sentry_sdk
import sentry_sdk.envelope
import sentry_sdk.transport
from fastapi.testclient import TestClient


class CapturingTransport(sentry_sdk.transport.Transport):
    """A Sentry transport that records event payloads instead of sending them.

    Lets a test assert an exception travelled the full SDK path (sampling,
    event processors, integrations) without anything leaving the host.
    """

    def __init__(self, options=None):
        super().__init__(options)
        self.events: list[dict] = []

    def capture_envelope(self, envelope: sentry_sdk.envelope.Envelope) -> None:
        for item in envelope.items:
            if item.type == "event" and item.payload.json is not None:
                self.events.append(item.payload.json)

    def flush(self, timeout, callback=None) -> None:
        pass

    def kill(self) -> None:
        pass


def _capturing_transport() -> CapturingTransport:
    """Re-init the global Sentry client with a recording transport."""
    transport = CapturingTransport()
    sentry_sdk.init(dsn="https://test@test.ingest.sentry.io/1", transport=transport)
    return transport


def test_sentry_init_ran_at_startup():
    """Importing `backend.main` instantiates `Telemetry`, which runs `sentry_sdk.init`."""
    import backend.main  # noqa: F401  (import triggers the Telemetry singleton)
    from backend import telemetry

    assert telemetry.Telemetry.initalized is True
    assert sentry_sdk.get_client() is not None


def test_explode_route_captures_exception_to_sentry():
    """The `/explode` forced-error route lands an event in the Sentry SDK."""
    from backend.main import app

    transport = _capturing_transport()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/explode")
    sentry_sdk.flush()

    # ErrorHandlingMiddleware swallows the exception and returns JSON 500.
    assert response.status_code == 500
    assert response.json()["detail"] == "internal server error"

    # Forced ZeroDivisionError must travel the full SDK path. Sentry integrations
    # may emit extra events too, so assert presence rather than exact count.
    captured_types = {
        value["type"]
        for event in transport.events
        for value in event.get("exception", {}).get("values", [])
    }
    assert "ZeroDivisionError" in captured_types, f"captured types: {captured_types}"


def test_healthy_route_captures_nothing():
    """A normal request must not generate a Sentry error event."""
    from backend.main import app

    transport = _capturing_transport()

    client = TestClient(app)
    response = client.get("/")
    sentry_sdk.flush()

    assert response.status_code == 200
    error_events = [e for e in transport.events if "exception" in e]
    assert error_events == [], f"unexpected error events: {error_events}"
