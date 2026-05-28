# Sentry status page - frontend + ops follow-ups

Companion to [todo-sentry.md](todo-sentry.md). Covers the website-side
rendering and the cross-service bonuses.

## Frontend (website repo)

New route: `src/pages/status.astro` (or `.tsx`, match existing convention).
Server-rendered at request time, hits the backend's `/sentry/*` endpoints,
caches the HTML at the edge for 5 min.

Layout roughly:

- Top: green/yellow/red status pill driven by "any critical unresolved issues
  in last 24h?"
- Section 1: summary tiles (events 24h/7d/30d, unresolved count, last release).
- Section 2: per-service table (from `/sentry/projects`).
- Section 3: top issues (from `/sentry/issues/top`), linked to Sentry.
- Section 4: recent releases (from `/sentry/releases/recent`).
- Footer: "data from Sentry, updated every N minutes, see repo on GitHub."

Mobile-first. The point of rolling this over a Grafana public dashboard is
that it actually reads well on a phone.

## Sequencing

1. Wire Sentry SDK into the backend, website build, and one other service
   (eco-mcp-app is the easy pick) so there's real data to query. Without
   this, the status page is empty and the whole thing is vapor.
2. Create the scoped SSM token, add to AGENTS.md inventory.
3. Ship backend `/sentry/summary` first. One endpoint, one test, deploy.
4. Add `/sentry/projects`, then `/sentry/issues/top`, then
   `/releases/recent`.
5. Frontend `/status` page consuming `/sentry/summary`. Iterate.
6. Write it up on coilysiren.me. Cross-post.

## Open questions

- Use Sentry's Sessions product for crash-free rate, or skip? Sessions need
  SDK-side opt-in and cost event volume. Decide after step 1 shows what
  volume looks like.
- Public dashboard on Grafana Cloud as a secondary surface for the "real"
  metrics (CPU, memory, pod restarts) when Alloy lands? Probably yes, but
  link to it from /status rather than embed.
- Should the status page show historical trends (events/day sparkline for
  30d)? Nice to have, not v1. Sentry's `stats_v2` endpoint supports it.

## Cross-service bonus

- **Sentry x Discord**: when unresolved count crosses a threshold, post to
  the `bots` channel. Low-noise replacement for email alerts.
- **Sentry x Bluesky**: weekly auto-skeet "homelab shipped N releases,
  caught M errors, here's what broke." Makes the o11y work legible.
- **Sentry x ambient statusline**: surface unresolved-issue count in the
  Claude Code statusline when working in any coilysiren repo.
