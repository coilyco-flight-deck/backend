# Features

Baseline of `coilysiren/backend`. Update when a headline feature changes.

## Purpose

A generic data-accessibility framework. An internal operational FastAPI service with Postgres behind it, exposing a small set of uniform modes - each a router with a generic endpoint and a self-documenting sentinel record. Internal-only: reachable on the tailnet through an in-Pod Tailscale sidecar, no public ingress. Ships as a container into the homelab k8s, OpenTelemetry to Honeycomb, errors to Sentry.

## Modes framework

- **One module per mode** - each module under `backend/modes/` owns a table, exposes an `APIRouter`, and ships an async `init(pool)` that creates its schema and upserts its sentinel.
- **Uniform mounting** - `main.py` mounts every mode router from `ALL_MODES`; the app lifespan opens the pool then calls each mode's `init`.
- **Sentinel pattern** - a shared `sentinels(mode, shape jsonb, note, created_at)` table. Each mode upserts one row describing its record shape, the ".keep-of-schemas" exemplar. Adding a mode is a router plus a sentinel - the extension point.
- **Bearer-token auth** - every mode route except `/health` validates `Authorization: Bearer <DATASTORE_TOKEN>`. Fails closed when no token is configured.

## Modes (v1)

- **health** - `GET /health`: DB connectivity (`SELECT 1`), the mounted modes, and every sentinel. The only unauthed route, since a liveness probe carries no token.
- **document** - append-only jsonb document store. `documents(id, namespace, key, payload jsonb, created_at)`, reads newest-first per `(namespace, key)`. Full CRUD.
- **queue** - `SELECT ... FOR UPDATE SKIP LOCKED` work queue. `queue_jobs` with `visible_at` for enqueue delay and post-claim visibility timeout. enqueue / claim / ack.
- **sql** - generic relational mode. Creates a real typed table `sql_<name>` from a column spec, tracked in a `sql_tables` registry, then CRUD its rows. Strict identifier regex plus a closed type allowlist - never interpolates an unvalidated identifier into SQL.
- **file** - temp-tier file storage on an ephemeral `emptyDir`. `POST /files/temp` writes a raw body and returns an id. Write-only by design, no read route in v1.

## CI release status

- **Release pipeline write** - the `build-publish-deploy` workflow POSTs `{repo, commit, status, run_url}` into the document mode, namespace `ci-status`, keyed by `<repo>@<commit>`. The POST goes to the internal tailnet host `api` from the tailnet-joined deploy job.
- **Mac-side poller** - reads by `{repo, commit}` and fires a local macOS notification. Lives in `coily` (tracked separately).

## Observability

- **OpenTelemetry tracing** - FastAPI auto-instrumentation, custom middleware spans.
- **Honeycomb OTLP export** with bearer auth.
- **Sentry** exception capture, prod-only DSN.
- **Structured request logs** - structlog JSON middleware.

## Platform and deployment

- **Container image** - Python 3.13 + uv multi-stage build.
- **Registry-free deploy** - CI builds the image, `docker save`s it, and streams the tarball into kai-server's k3s containerd over a tailscale-ssh tunnel, then `set image` + rollout. No GHCR pull, no imagePullSecret. Mirrors the galaxy-gen / repo-recall rig.
- **Kubernetes manifests** - app Deployment, Postgres StatefulSet + 1Gi PVC, ClusterIP + headless DB Service, ExternalSecrets, an `emptyDir` temp tier for the file mode. No Ingress.
- **Internal-only** - reachable on the tailnet through the in-Pod Tailscale sidecar at host `api`. No public ingress, no TLS, no TrustedHost allowlist. CORS stays permissive since the surface is tailnet-internal.
- **Secret sync** - Postgres password / datastore token / Sentry DSN / Tailscale authkey from AWS SSM, 1h refresh.
- **Rate limiting** - slowapi, 10 req/s on `/`.

## Test endpoints

- `GET /` - smoke test.
- `GET /explode` - forced exception, smoke test for Sentry and the error middleware.

## See also

- [README.md](../README.md) - human-facing intro.
- [AGENTS.md](../AGENTS.md) - agent-facing operating rules.
- [.coily/coily.yaml](../.coily/coily.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os-kai#313](https://github.com/coilysiren/agentic-os-kai/issues/313).
