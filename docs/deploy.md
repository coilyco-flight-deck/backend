# Deploy pipeline

How `coilysiren/backend` ships into the homelab k3s cluster. The rationale that used to live as inline comments in [`.forgejo/workflows/build-publish-deploy.yml`](../.forgejo/workflows/build-publish-deploy.yml) lives here, so a YAML key-sorter can never drift it off its target. The cluster manifest is covered in [docs/deploy-cluster.md](deploy-cluster.md); the cross-repo homelab rig in [`infrastructure/docs/k3s-deploy-notes.md`](../../infrastructure/docs/k3s-deploy-notes.md).

## build-publish-deploy

The Forgejo Actions workflow runs `test` then `deploy` on push to `main`.

- **Install deploy tooling** - the `docker` runner label resolves to `node:20-bookworm`, which ships git + curl but no docker CLI, kubectl, or jq. The step pulls them in as static binaries (apt-free, so no daemon postinst runs in the job container). docker talks to the DinD sidecar, kubectl rolls the deployment, jq builds the status payload.
- **Resolve docker host** - the DinD sidecar shares the runner pod's netns and listens on `:2375` there, but the job container sits on a separate per-workflow docker bridge. The inherited `DOCKER_HOST=tcp://localhost:2375` points at the job container's own loopback, not dockerd. dockerd is reachable at the job container's default-route gateway (the pod netns), so the step probes candidates and pins the first that answers. See backend#26.
- **Build and push** - builds the image and pushes it to the in-cluster registry at `192.168.0.194:30500`. The DinD sidecar carries `--insecure-registry=192.168.0.194:30500`, so the plain-http push to the NodePort registry round-trips. No tailnet join, no GHCR, no docker-save sideload. Uses the legacy builder, since the static docker CLI ships no buildx plugin (BuildKit `--progress` / inline cache unavailable); a plain build against the daemon is enough for this single image. See infrastructure#168, infrastructure#171.
- **Roll deployment** - the kubeconfig (base64 in the `DEPLOY_KUBECONFIG` Forgejo secret) points at the k3s API on the LAN IP `192.168.0.194:6443` (in the cert SANs) and authenticates as the deployer ServiceAccount. The app pod is pinned to kai-server, where `registries.yaml` has the insecure-registry entry, so the cluster-side pull of `192.168.0.194:30500/...` lands on that node. See infrastructure#171.
- **Report status** - writes build/deploy status into the `document` mode, POSTing to the internal host `api` over the LAN-reachable in-cluster service. The Mac-side poller reads `namespace=ci-status`, `key=<repo>@<commit>`. See backend#65, backend#77.

## See also

- [docs/deploy-cluster.md](deploy-cluster.md) - the cluster manifest walkthrough.
- [docs/FEATURES.md](FEATURES.md) - feature inventory, including the platform/deploy summary.
- [infrastructure/docs/k3s-deploy-notes.md](../../infrastructure/docs/k3s-deploy-notes.md) - cross-repo homelab rig and pitfalls.
