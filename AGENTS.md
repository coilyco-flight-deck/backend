# Agent instructions

Workspace conventions load globally via `~/.claude/CLAUDE.md` -> `agentic-os-kai/AGENTS.md`. This file covers only what is specific to this repo.

---

Deploy config (Dockerfile, Makefile, `deploy/main.yml`, `.github/workflows/build-and-publish.yml`, Tailscale/k3s secrets) follows the canonical homelab rig documented in [`infrastructure/docs/k3s-deploy-notes.md`](../infrastructure/docs/k3s-deploy-notes.md). When you resolve a new pitfall, add it there, not here.

---

## Post-push follow-up (auto-schedule)

Per the workspace "Default to proactive scheduling" rule: after pushing to `main`, schedule a wake-up to verify the build-publish-deploy job reached steady state on kai-server. CI runs docker build + push + k8s rollout; total time is ~6-12 min.

- **Cadence**: 720s (12 min) after push. Build is the slow part; rollout is fast. 12 min lands after the long tail.
- **Verify CI**: `ward-kdl ops forgejo action ci-watch` watches the latest `build-publish-deploy` run to completion and exits non-zero if a job fails. If it is still in progress, re-schedule once at +300s; if it failed, surface and stop.
- **Verify rollout**: `ward-kdl ops kubectl rollout status deployment/coilysiren-backend-app -n coilysiren-backend --timeout=2m`.
- **Skip** for docs-only pushes (no rebuild produces no behavior change to wait on).

## Commands

Route every dev command through ward, which reads [`.ward/ward.yaml`](.ward/ward.yaml) (run verbs with `ward exec <verb>`). The lockdown denies bare invocations of the underlying tools (`make`, `uv`, `npm`, `dotnet`, `docker`, `cargo`, etc.). Add new verbs to that file before invoking them.

## Scope

Backend-specific operating notes for agents. Workspace conventions live in `../AGENTS.md`.

## Project shape

FastAPI + Postgres modes framework. See [README.md](README.md) and [docs/FEATURES.md](docs/FEATURES.md).

## Repo boundaries

Internal-only service. Deploy config follows the canonical homelab rig, not this repo's docs.

## Validation

`ward exec test` runs the pytest suite. Pre-commit (`pre-commit run --all-files`) covers ruff, mypy, trufflehog, and the agentic-os documentation/catalog hooks.

## Safety

Bearer-token auth on every mode route except `/health`. Fails closed when `DATASTORE_TOKEN` is absent.

## Cross-repo contracts

`build-publish-deploy` workflows in other coilysiren repos POST CI status into this backend's `document` mode under namespace `ci-status`.

## Release

CI builds the image and pushes it to the in-cluster registry (plain http via the DinD sidecar), then rolls the deployment as the deployer ServiceAccount. No GHCR, no docker-save sideload. See [docs/deploy.md](docs/deploy.md).

## Agent rules

Workspace defaults from `../AGENTS.md` apply. Repo-local additions are documented in the sections above.

## See also

- [README.md](README.md) - human-facing intro.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands (`ward exec`). Agents route through ward, not bare `make` / `uv` / `python` / `npm` / `cargo` / `dotnet`.

Cross-reference convention from [coilysiren/agentic-os-kai#313](https://github.com/coilyco-bridge/agentic-os-kai/issues/313).
