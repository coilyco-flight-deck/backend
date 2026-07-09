# Deploy pipeline

How `coilysiren/backend` ships its image and where the Kubernetes rollout lives. The workflow in [`.forgejo/workflows/build-publish-deploy.yml`](../.forgejo/workflows/build-publish-deploy.yml) now does test, build, push, and status reporting only. The deploy repo owns the live rollout manifest at [coilyco-bridge/deploy/services/backend/deploy/main.yml](https://forgejo.coilysiren.me/coilyco-bridge/deploy/src/branch/main/services/backend/deploy/main.yml).

## build-publish-deploy

The Forgejo Actions workflow runs `test` then `publish` on push to `main`.

- **Run in dev-base** - the jobs run inside the pinned aos dev-base image, which already ships uv, Python, Docker CLI, Node, and jq. That keeps the image as the single bootstrap surface for the job's runtime tools. docker talks to the DinD sidecar, jq builds the status payload.
- **Build and push** - builds the image and pushes it to the in-cluster registry at `192.168.0.194:30500`. The DinD sidecar carries `--insecure-registry=192.168.0.194:30500`, so the plain-http push to the NodePort registry round-trips. No tailnet join, no GHCR, no docker-save sideload. Uses the legacy builder, since the static docker CLI ships no buildx plugin (BuildKit `--progress` / inline cache unavailable); a plain build against the daemon is enough for this single image. See infrastructure#168, infrastructure#171.
- **Report status** - writes build status into the `document` mode, POSTing to the internal host `api` over the LAN-reachable in-cluster service. The Mac-side poller reads `namespace=ci-status`, `key=<repo>@<commit>`. See backend#65, backend#77.

## See also

- [docs/deploy-cluster.md](deploy-cluster.md) - pointer to the live cluster manifest in the deploy repo.
- [docs/FEATURES.md](FEATURES.md) - feature inventory, including the platform/deploy summary.
- [coilyco-bridge/deploy/services/backend/README.md](https://forgejo.coilysiren.me/coilyco-bridge/deploy/src/branch/main/services/backend/README.md) - the rollout surface that owns the namespace and manifest.
