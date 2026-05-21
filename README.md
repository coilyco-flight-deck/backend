# backend

FastAPI service behind `api.coilysiren.me`. Hosts the ambient personal CRUD datastore - a generic `items` table in Postgres with authed CRUD endpoints in front of it. First consumer is the CI release pipeline writing build/deploy status that the Mac side polls. Design: [coilysiren/backend#65](https://github.com/coilysiren/backend/issues/65), [coilysiren/agentic-os-kai#657](https://github.com/coilysiren/agentic-os-kai/issues/657).

Deploys to the k3s homelab via the canonical rig in [infrastructure/docs/k3s-deploy-notes.md](../infrastructure/docs/k3s-deploy-notes.md).

## Install

```bash
brew install uv jq
brew install --cask docker
```

## Environment

Create `.env`:

```bash
PRODUCTION=false
DATASTORE_TOKEN=dev-token              # bearer token the /items routes validate
DATABASE_URL=postgresql://backend:backend@localhost:5432/backend
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

curl -s -X POST http://localhost:4000/items \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"namespace":"ci-status","key":"demo","payload":{"status":"ok"}}' | jq

curl -s http://localhost:4000/items/ci-status/demo \
  -H "Authorization: Bearer dev-token" | jq
```

## Test

```bash
make test
```

## API

All `/items` routes require an `Authorization: Bearer <DATASTORE_TOKEN>` header.

- `POST /items` - append a document. Body `{namespace, key, payload}`.
- `GET /items/{namespace}` - list a namespace, newest first. Optional `?key=` and `?limit=`.
- `GET /items/{namespace}/{key}` - newest document for a key, or 404.
- `DELETE /items/{namespace}/{key}` - delete every document for a key.

## Commands

Dev commands are declared in [`.coily/coily.yaml`](.coily/coily.yaml). Run them as `coily exec <verb>`.

## See also

- [AGENTS.md](AGENTS.md) - agent-facing operating rules.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [.coily/coily.yaml](.coily/coily.yaml) - allowlisted commands. Agents route through coily, not bare `make` / `uv` / `python` / `npm` / `cargo` / `dotnet`.

Cross-reference convention from [coilysiren/agentic-os-kai#313](https://github.com/coilysiren/agentic-os-kai/issues/313).
