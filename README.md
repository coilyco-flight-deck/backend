# backend

A generic data-accessibility framework. An internal operational backend with Postgres behind it, exposing a small set of uniform **modes**, each a FastAPI router with a generic endpoint and a self-documenting sentinel record. Internal-only - reachable on the tailnet via an in-Pod Tailscale sidecar, no public ingress. Design: [coilysiren/backend#77](https://github.com/coilysiren/backend/issues/77), [coilysiren/backend#65](https://github.com/coilysiren/backend/issues/65), [coilysiren/agentic-os-kai#657](https://github.com/coilysiren/agentic-os-kai/issues/657).

Deploys to the k3s homelab via the canonical rig in [infrastructure/docs/k3s-deploy-notes.md](../infrastructure/docs/k3s-deploy-notes.md).

## Modes

Each mode lives in `backend/modes/`, owns one table, and ships an `APIRouter` plus an async `init(pool)` that creates its schema and upserts a sentinel row. Adding a mode is a new module plus an entry in `ALL_MODES` - nothing else changes.

- **health** - `GET /health`: DB connectivity, the mounted modes, and every sentinel. The only unauthed route - it is the liveness probe.
- **document** - append-only jsonb document store keyed by `(namespace, key)`. `POST /document`, `GET /document/{namespace}`, `GET /document/{namespace}/{key}`, `DELETE /document/{namespace}/{key}`.
- **queue** - `SELECT ... FOR UPDATE SKIP LOCKED` work queue. `POST /queue/{namespace}` enqueue, `POST /queue/{namespace}/claim` claim, `DELETE /queue/{namespace}/{id}` ack. `visible_at` carries enqueue delay and post-claim visibility timeout.
- **sql** - generic relational mode. `POST /sql/tables` creates a real typed table `sql_<name>` from a column spec, `GET /sql/tables` lists the registry, `POST /sql/tables/{name}/rows` and `GET /sql/tables/{name}/rows` CRUD its rows. Strict identifier regex plus a closed type allowlist - the "dispatch a new table type from mobile" surface.
- **file** - temp-tier file storage. `POST /files/temp` writes a raw body to an ephemeral `emptyDir`, returns an id. Write-only by design - no read route in v1.

### Sentinel pattern

A shared `sentinels(mode, shape jsonb, note, created_at)` table. Each mode upserts one row on `init` describing its record shape - the ".keep-of-schemas" exemplar that keeps the framework self-documenting. `GET /health` returns them all.

## Auth

Every mode route except `/health` requires an `Authorization: Bearer <DATASTORE_TOKEN>` header. The token lives in AWS SSM at `/coilysiren/backend/datastore-token`. Auth fails closed - with no token configured the routes return 503 rather than open up.

## Install

```bash
brew install uv jq
brew install --cask docker
```

## Environment

Create `.env`:

```bash
DATASTORE_TOKEN=dev-token              # bearer token every mode route validates
DATABASE_URL=postgresql://backend:backend@localhost:5432/backend
FILE_TEMP_DIR=/tmp/backend-files       # temp tier for the file mode
OTEL_SDK_DISABLED=true
```

`DATABASE_URL` can be left unset and assembled from `PGHOST` / `PGUSER` / `PGPASSWORD` / `PGDATABASE` / `PGPORT` instead, which is how the k8s manifest injects it.

A local Postgres for development:

```bash
docker run -d --name backend-db -p 5432:5432 \
  -e POSTGRES_USER=backend -e POSTGRES_PASSWORD=backend -e POSTGRES_DB=backend \
  postgres:17
```

## Run

```bash
make build-native    # uv lock + uv sync
make run-native      # uvicorn on :4000

curl -s http://localhost:4000/health | jq

curl -s -X POST http://localhost:4000/document \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"namespace":"ci-status","key":"demo","payload":{"status":"ok"}}' | jq

curl -s http://localhost:4000/document/ci-status/demo \
  -H "Authorization: Bearer dev-token" | jq
```

## Test

```bash
make test
```

Pure tests run without a database. The DB-integration tests are skipped unless `BACKEND_TEST_DATABASE_URL` points at a throwaway Postgres.

## Commands

Dev commands are declared in [`.coily/coily.yaml`](.coily/coily.yaml). Run them as `coily exec <verb>`.

## See also

- [AGENTS.md](AGENTS.md) - agent-facing operating rules.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [.coily/coily.yaml](.coily/coily.yaml) - allowlisted commands. Agents route through coily, not bare `make` / `uv` / `python` / `npm` / `cargo` / `dotnet`.

Cross-reference convention from [coilysiren/agentic-os-kai#313](https://github.com/coilysiren/agentic-os-kai/issues/313).
