# Features

Baseline of `coilysiren/backend`. Update when a headline feature changes.

## Purpose

FastAPI service behind `api.coilysiren.me`. Hosts the ambient personal CRUD datastore: a generic `items` table in Postgres for small JSON documents, with authed HTTP CRUD in front. Ships as a container into the homelab k8s, OpenTelemetry to Honeycomb, errors to Sentry.

## Ambient datastore

- **Generic items table** - `items(id, namespace, key, payload jsonb, created_at)` in Postgres. Schemaless documents plus real queries.
- **Append-only writes** - each `POST` inserts a row; reads return the newest row per `(namespace, key)`.
- **CRUD API** - `POST /items`, `GET /items/{namespace}`, `GET /items/{namespace}/{key}`, `DELETE /items/{namespace}/{key}`.
- **Bearer-token auth** - every `/items` route validates `Authorization: Bearer <DATASTORE_TOKEN>`. Fails closed when no token is configured.
- **Schema on startup** - the table and its index are created idempotently when the connection pool opens.

## First consumer: CI release status

- **Release pipeline write** - the `build-publish-deploy` workflow POSTs `{repo, commit, status, run_url}` into namespace `ci-status`, keyed by `<repo>@<commit>`.
- **Mac-side poller** - reads by `{repo, commit}` and fires a local macOS notification. Lives in `coily` (tracked separately).

## Observability

- **OpenTelemetry tracing** - FastAPI auto-instrumentation, custom middleware spans.
- **Honeycomb OTLP export** with bearer auth.
- **Sentry** exception capture, prod-only DSN.
- **Structured request logs** - structlog JSON middleware.

## Platform and deployment

- **Container image** - Python 3.13 + uv multi-stage build.
- **Registry-free deploy** - CI builds the image, `docker save`s it, and streams the tarball into kai-server's k3s containerd over a tailscale-ssh tunnel, then `set image` + rollout. No GHCR pull, no imagePullSecret. Mirrors the galaxy-gen / repo-recall rig.
- **Kubernetes manifests** - app Deployment, Postgres StatefulSet + 5Gi PVC, ClusterIP + headless DB Service, Traefik Ingress, ExternalSecrets.
- **Secret sync** - Postgres password / datastore token / Sentry DSN / Tailscale authkey from AWS SSM, 1h refresh.
- **Tailnet** - in-Pod Tailscale sidecar in kernel mode.
- **TLS** - cert-manager + Let's Encrypt via Traefik.
- **CORS / trusted hosts** - dev permissive, prod restricted to `coilysiren.me`.
- **Rate limiting** - slowapi, 10 req/s on `/`, 20 req/s on `/items`.

## Test endpoints

- `GET /` - healthcheck.
- `GET /explode` - forced exception, smoke test for Sentry and the error middleware.

## See also

- [README.md](../README.md) - human-facing intro.
- [AGENTS.md](../AGENTS.md) - agent-facing operating rules.
- [.coily/coily.yaml](../.coily/coily.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os-kai#313](https://github.com/coilysiren/agentic-os-kai/issues/313).
