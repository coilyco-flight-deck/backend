# Sentry status page

Powers a public `/status` route on coilysiren.me. Backend pulls Sentry's
API, frontend renders. This file is the backend plan; frontend, sequencing,
and cross-service bonus live in [todo-sentry-frontend.md](todo-sentry-frontend.md).

Credentials: scoped read-only auth token in AWS SSM at
`/sentry/readonly-token`. Add to the SSM inventory in `../AGENTS.md` when
the token is created. Token scopes: `event:read`, `project:read`,
`org:read`. Nothing more.

Org slug and project slugs are not secret; hardcode or surface via env
(`SENTRY_ORG`, `SENTRY_PROJECTS`). Default base URL
`https://sentry.io/api/0/`.

## Why this exists

Sentry has no first-class public dashboard. Everything in-product is
auth-gated. The goal is a public, read-only "how's the homelab" surface
that makes the o11y work visible without handing out org access.

Secondary goal: the repo itself is part of the o11y-backfill story against
my resume. Ship it, write it up, cross-link from the website.

## Backend (this repo)

New module: `backend/sentry.py`. FastAPI router mounted under `/sentry`.

1. **`GET /sentry/summary`** - rollup for the full org. Returns total
   events last 24h / 7d / 30d, unresolved issue count (org-wide), latest
   release name + age, crash-free session rate if sessions are enabled
   else null.
2. **`GET /sentry/projects`** - per-project breakdown. For each project in
   `SENTRY_PROJECTS`: name, event count 7d, unresolved count, last seen
   event timestamp. Powers the "services" table on the frontend.
3. **`GET /sentry/issues/top`** - top N unresolved issues by event count,
   last 7d. Title, culprit, event count, first seen, last seen, permalink.
   N=10 default, cap at 25.
4. **`GET /sentry/releases/recent`** - last 5 releases across the org.
   Version, date created, project count, new issue count. Lets the
   frontend show "what shipped recently and did it break anything."

All responses JSON. All cached in Redis (already available, see
`backend/cache.py`) with a 5-10 minute TTL. Sentry's rate limits are
generous but a HN hug would still blow through them.

## Safety before shipping

Sentry returns more than a public page should show. Strip or allowlist on
the backend, not the frontend, so a leak would require a backend change
(auditable in git).

- **Strip**: stack trace frames, request bodies, breadcrumbs, user context,
  IP, env vars, server names, file paths.
- **Keep**: issue title, culprit (usually just the function name), event
  count, first/last seen, permalink (`https://sentry.io/...` - fine to
  expose, it's auth-gated on Sentry's side).
- **Consider**: truncate issue titles to N chars in case they embed prod
  data.
- **Deny-list**: hardcode a list of project slugs that are never exposed,
  as a backstop in case `SENTRY_PROJECTS` ever gets misconfigured.
