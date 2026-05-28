# AWS wishlist

Credentials: boto3 already used in `../infrastructure/` (`eco.py`, `k8s.py`, `llama.py`).
SSM Parameter Store and S3 are the primary services in use today.

## Ideas

1. **Production secrets via SSM** — replace `.env` in production with SSM Parameter
   Store reads at startup. Already the pattern for `/eco/server-api-token`.
2. **S3-backed cache layer** — for expensive endpoints (emoji-summary, popularity), store
   completed results in S3 with a content-addressed key. Redis stays for hot data.
3. **Personal data lake** — nightly export of bsky followers, GitHub stars, YouTube
   subs, Steam play time into S3 as parquet. Then I can run ad-hoc analytics on the
   notebook.ipynb against a real history, not just "right now".
4. **CloudWatch dashboards** — push the structlog JSON output into CloudWatch Logs and
   build a personal dashboard for endpoint latency + error rate.
5. **Lambda cron workers** — port the `worker.py` background tasks to Lambda + EventBridge
   so I'm not tying up the FastAPI process for long-running work.
6. **SES for self-email** — send myself the daily briefings (see `anthropic.md`) via SES
   instead of standing up an SMTP server.
7. **Route53 dynamic DNS** — point a personal subdomain at my home IP and update it via
   a tiny Lambda when it changes. Useful for the kai-server box.

## Cross-service bonus

- **AWS × Anthropic (Claude Code)**: store every Cowork run's transcript in S3 keyed by
  date, so I have a searchable archive of what I've asked Claude to do.
- **AWS × GitHub**: nightly Lambda that snapshots the README + topics of every public
  repo I own to S3. Cheap "wayback machine" for my own work.
- **AWS × Bluesky**: dump my full bsky post history to S3 weekly as JSONL, so the
  notebook can do longitudinal analysis (sentiment over time, posting cadence, etc.).
- **AWS × Steam**: snapshot my Steam library + hours-played to S3 daily — multi-year
  graphs of "what I actually played" become possible.
- **AWS × Discord**: route a private SNS topic into a Discord channel via webhook for a
  personal "ops alerts" feed (deploy succeeded, cron failed, S3 nearing quota, etc.).

## Personalized for Kai

- **Journal-to-S3 archival pipeline** — nightly Lambda that snapshots
  `coilyco-vault/Obsidian Vault/Journal/*.md` to S3 (encrypted, versioned). The journal
  is high-stakes data — local-only is a mistake. Frontmatter parsed into a small index
  table for fast queries.
- **People/ CRM data lake** — same pattern for `People/`. With ~100 files, a parquet
  export to S3 unlocks "who haven't I talked to in 6 months" in one query instead of
  a vault grep. Feeds the Personal CRM ideas in `discord.md` and `anthropic.md`.
- **AI SRE prototype platform** — a small Lambda-based runbook executor that takes
  Datadog/Sentry alerts as input and runs Claude-Code-driven triage. The tangible thing
  to point at when making the AI SRE pitch — pitch + code beats pitch alone.
- **Gauntlet agent telemetry** — push the 20 running Gauntlet agents' outputs into
  CloudWatch Logs Insights, build a single dashboard. Gives you the screenshot for the
  coilysiren.me writeup and avoids reinventing o11y.
- **MFA backup vault** — KMS-encrypted parameter in SSM holding your TOTP seeds (or a
  reference to a Backblaze B2 bundle). You flagged "I need to backup my MFA. Not today
  though" — give yourself a one-command path so it's a 5-minute job when you do.
- **ADU finance tracker** — small DynamoDB table holding ADU savings progress against a
  target, updated by a Lambda that pulls from Plaid or a manual CSV drop. Endpoint feeds
  a progress bar on the website.
- **Medical follow-up reminders** — EventBridge rules for upcoming checkpoints
  (appointments, recovery milestones, multi-year plans) so they aren't carried in
  your head.
