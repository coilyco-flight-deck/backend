# backend

A generic data-accessibility framework. An internal operational backend with Postgres behind it, exposing a small set of uniform **modes**, each a FastAPI router with a generic endpoint and a self-documenting sentinel record. Internal-only - reachable on the tailnet via an in-Pod Tailscale sidecar, no public ingress. Design: [coilysiren/backend#77](https://github.com/coilyco-flight-deck/backend/issues/77), [coilysiren/backend#65](https://github.com/coilyco-flight-deck/backend/issues/65), [coilysiren/agentic-os-kai#657](https://github.com/coilyco-bridge/agentic-os-kai/issues/657).

The source CI builds and publishes the image. The Kubernetes rollout lives in [coilyco-bridge/deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy), which owns the runtime manifest for this service.

## Modes

Each mode lives in `backend/modes/`, owns one table, and ships an `APIRouter` plus an async `init(pool)` that creates its schema and upserts a sentinel row. Adding a mode is a new module plus an entry in `ALL_MODES` - nothing else changes.

- **health** - `GET /health`: DB connectivity, the mounted modes, and every sentinel. The only unauthed route - it is the liveness probe.
- **document** - append-only jsonb document store keyed by `(namespace, key)`. `POST /document`, `GET /document/{namespace}`, `GET /document/{namespace}/{key}`, `DELETE /document/{namespace}/{key}`.
- **queue** - `SELECT ... FOR UPDATE SKIP LOCKED` work queue. `POST /queue/{namespace}` enqueue, `POST /queue/{namespace}/claim` claim, `DELETE /queue/{namespace}/{id}` ack. `visible_at` carries enqueue delay and post-claim visibility timeout.
- **sql** - generic relational mode. `POST /sql/tables` creates a real typed table `sql_<name>` from a column spec, `GET /sql/tables` lists the registry, `POST /sql/tables/{name}/rows` and `GET /sql/tables/{name}/rows` CRUD its rows.
- **file** - temp-tier file storage. `POST /files/temp` writes a raw body to an ephemeral `emptyDir`, returns an id. Write-only by design.

### Sentinel pattern

A shared `sentinels(mode, shape jsonb, note, created_at)` table. Each mode upserts one row on `init` describing its record shape - the ".keep-of-schemas" exemplar that keeps the framework self-documenting. `GET /health` returns them all.

## Auth

Every mode route except `/health` requires an `Authorization: Bearer <DATASTORE_TOKEN>` header. The token lives in AWS SSM at `/coilysiren/backend/datastore-token`. Auth fails closed - with no token configured the routes return 503 rather than open up.

## Develop

Install, run, and test instructions live in [docs/dev.md](docs/dev.md). Dev commands are declared in [`.ward/ward.yaml`](.ward/ward.yaml); run them as `ward exec <verb>`.

## See also

- [AGENTS.md](AGENTS.md) - agent-facing operating rules.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [docs/dev.md](docs/dev.md) - local install, env, run, test.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os-kai#313](https://github.com/coilyco-bridge/agentic-os-kai/issues/313).
