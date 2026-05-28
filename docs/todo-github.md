# GitHub wishlist

Credentials: `gh` CLI is already authenticated (see `../website/fetch-now-data.js`).
Likely env var: `GITHUB_TOKEN`.

## Ideas

1. **Commit heatmap JSON** — endpoint that returns a year of commit activity across all my
   repos as a flat array, ready for a calendar-heatmap component on the website.
2. **"What I shipped this week" digest** — aggregate merged PRs + closed issues across all
   my repos into a weekly markdown summary. Cache in Redis, regenerate on a cron.
3. **Star-graph deltas** — track stars added/lost per repo per day, expose a sparkline
   endpoint. Surfaces which old projects are getting rediscovered.
4. **Auto-README badges** — endpoint that generates SVG badges (last commit, open issues,
   line count) for any of my repos so I can embed them anywhere.
5. **Issue triage inbox** — single feed of every open issue across every repo I own,
   sorted by staleness, so I can blow through triage in one sitting.
6. **Repo "now" tag** — let me PATCH a single endpoint to set a "currently working on"
   repo, which then gets surfaced on the website /now page.
7. **Dependabot fan-out summary** — count open Dependabot PRs across all repos, group by
   ecosystem, so I can decide whether to do a dependency-update sweep.

## Cross-service bonus

- **GitHub × Bluesky**: auto-post a skeet whenever I tag a release on a public repo
  (`coilysiren-bot.bsky.social` is already set up).
- **GitHub × Discord**: pipe new issues on selected repos into a Discord channel via the
  existing `discord-bot`, with a 👀 reaction = "I'll take it".
- **GitHub × YouTube**: when I publish a YouTube video whose title matches a repo name,
  auto-comment a link to the video in that repo's README.
- **GitHub × Anthropic (Claude Code)**: nightly Claude Code job that opens a draft PR with
  a "stale TODO sweep" — finds TODOs older than 6 months and proposes deletions.

## Personalized for Kai

- **Gauntlet visibility pipeline** — Gauntlet has 20 agents running but no shipped
  writeup. An endpoint that turns the latest Gauntlet run results into a draft markdown
  post (commit log + agent outputs + a one-paragraph framing) staged for coilysiren.me.
  This is the "force-multiplier IC" version of "I'll write that up later."
- **AI SRE business-case generator** — pull commits + PRs + linked issues from a
  designated `ai-sre` repo and produce a weekly "what AI SRE shipped + what it cost in
  tokens" digest. Turn the pitch into an artifact.
- **Cross-repo "force multiplier" dashboard** — for the personal repo set, a single page
  that surfaces: what changed this week, what's blocked, what's stale. Designed around
  your "compounding technical impact" frame, not GitHub's.
- **"Kai-shaped repo template"** — given a repo name, scaffold a new repo with your
  standard Python+Poetry+pyproject layout, OTel/structlog wiring like this backend, and
  a CLAUDE.md based on your USER.md. One command instead of an afternoon.
