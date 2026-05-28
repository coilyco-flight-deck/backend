# Local development

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

`DATABASE_URL` can be left unset and assembled from `PGHOST` / `PGUSER` /
`PGPASSWORD` / `PGDATABASE` / `PGPORT` instead, which is how the k8s
manifest injects it.

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

Pure tests run without a database. The DB-integration tests are skipped
unless `BACKEND_TEST_DATABASE_URL` points at a throwaway Postgres.
