# Cluster manifest

The rationale behind [`deploy/main.yml`](../deploy/main.yml), moved out of inline YAML comments so a key-sorter can't drift it off its target. The release pipeline that applies it is covered in [docs/deploy.md](deploy.md). The manifest is the full namespace, applied with `${NAME}` / `${IMAGE}` substituted.

## Release access

- **Deployer ServiceAccount / Role / RoleBinding** - the CI deploy job authenticates as this SA to roll the app Deployment over the LAN. The kubeconfig in `DEPLOY_KUBECONFIG` is built from this SA's token Secret. No tailnet join, no SSH. See backend#25.
- **deployer-token Secret** - long-lived token for the deployer SA. Kubernetes populates `token`, `ca.crt`, and `namespace`; the `DEPLOY_KUBECONFIG` Forgejo secret is built from its `ca.crt` + `token`. Regenerate the kubeconfig if rotated. The token never lives in git. See backend#25.
- **No pull-secret** - the image is pushed to the in-cluster registry over plain http and pulled by kai-server's containerd via its insecure-registry entry. See infrastructure#171 and [docs/deploy.md](deploy.md).

## Secrets from SSM

Each `ExternalSecret` syncs one AWS SSM parameter into the namespace on a 1h refresh.

- **`${NAME}-db`** - `/coilysiren/backend/db-password` (SecureString). Backs the Postgres StatefulSet (`POSTGRES_PASSWORD`) and the app's asyncpg pool (`PGPASSWORD`).
- **`${NAME}-datastore-token`** - `/coilysiren/backend/datastore-token` (SecureString). Bearer token for every mode route, validated by `backend/datastore.py`'s `require_token` dependency. The CI pipeline and the Mac-side poller send it.
- **`${NAME}-sentry`** - `/sentry-dsn/backend`. Consumed by `backend/telemetry.py`'s `sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"))`.
- **`ts-authkey`** - `/coilysiren/backend/ts-authkey`. Tailnet auth key for the app pod, minted by `terraform/tailscale-devices/` in infrastructure under the short name `backend`.

## Postgres

- **Headless Service** - `${NAME}-db` clusterIP `None`, for the StatefulSet's pod-DNS. The app reaches the database at `${NAME}-db` inside the namespace. Same pattern as the forgejo deploy in infrastructure.
- **pg_hba.conf ConfigMap** - in-cluster only. The app (pod CIDR `10.42.0.0/16`) authenticates with `scram-sha-256`; loopback keeps `trust` for in-pod maintenance. The db pod is no longer on the tailnet, so there is no passwordless tailnet path. The StatefulSet runs `postgres` with `hba_file=/etc/postgresql/pg_hba.conf`, a custom path outside PGDATA. See backend#79.
- **Storage** - `5Gi` matches the live PVC. `volumeClaimTemplates` is immutable, so this can't be lowered without recreating the volume. The KV store holds small JSON docs (single-digit MB in practice).

## App Deployment

- **Node pinning** - `nodeSelector` is kai-server because `/dev/net/tun` for the ts sidecar lives there (native Linux 6.8); WSL2 nodes don't expose it.
- **Image pull** - `imagePullPolicy: Always`, so each rolled `${git-hash}` tag is fetched fresh from the in-cluster registry.
- **File mode temp tier** - `FILE_TEMP_DIR=/data/temp` backed by an ephemeral `emptyDir`. Write-only, gone on pod restart, no durable tier in v1.
- **ts sidecar** - kernel mode, `TS_HOSTNAME=api`. Same pattern as canary repo-recall (infrastructure#201) and eco-mcp-app.
- **Service** - no Ingress. Internal-only, reachable on the tailnet via the in-pod Tailscale sidecar (`TS_HOSTNAME=api`). No public TLS, no cert-manager.

## See also

- [docs/deploy.md](deploy.md) - the release pipeline walkthrough.
- [infrastructure/docs/k3s-deploy-notes.md](../../infrastructure/docs/k3s-deploy-notes.md) - cross-repo homelab rig.
