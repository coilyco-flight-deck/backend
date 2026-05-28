# Discord wishlist

Credentials: bot token in `../discord-bot/`. Env var: `DISCORD_BOT_TOKEN`.

## Ideas

1. **Personal command bus** — a `!remind`, `!todo`, `!note` command set that writes into
   a Redis-backed personal scratchpad I can read from anywhere.
2. **Channel-to-RSS** — export a chosen channel's pinned messages as an RSS feed, so I
   can subscribe to "things I starred in Discord" from any reader.
3. **Reaction archive** — log every message I react to with ⭐, build a personal
   "favorites" feed across every server I'm in.
4. **Lurker stats** — for servers I'm in, show me which channels actually had activity
   today so I can stop opening dead ones.
5. **Voice-channel presence log** — record (locally) when I joined and left voice
   channels. Surfaces "I spent 14 hours in voice chat this week, maybe go outside".
6. **Quote bot** — `!quote @user` randomly pulls one of their messages from the last
   year. Server in-jokes, immortalized.
7. **Cross-server DM digest** — daily summary of unread DMs across every server, so I
   stop missing pings.

## Cross-service bonus

- **Discord × GitHub**: `!issue` command opens a GitHub issue in a chosen repo from a
  Discord message, including the message author and a permalink.
- **Discord × Bluesky**: a channel that mirrors my Bluesky notifications so I can
  triage replies without opening the app.
- **Discord × Steam**: rich-presence-style status updates posted to a channel — "Kai
  started playing X" — opt-in per game.
- **Discord × Anthropic (Claude Code)**: `!claude {prompt}` command that dispatches a
  Cowork task and posts the result back when it finishes. Personal Claude over Discord.
- **Discord × YouTube**: post new uploads from a watchlist of channels into a
  `#video-club` channel for async watchalongs.

## Personalized for Kai

- **Personal CRM pings via Discord DM** — the Obsidian People/ directory has ~100
  files. A daily DM to yourself: "you haven't pinged {name} in {N} months — last topic:
  {x}." Pulled from People/ frontmatter. Lowers the cost of staying in touch.
- **Eco Sirens server console** — slash commands in the existing `discord-bot` to
  start/stop/snapshot the Eco server, list players, broadcast announcements. Eliminates
  the SSH step before the cycle starts end of this week.
- **AI-psychosis self-monitor channel** — a private channel where the bot posts a daily
  self-check ("any sycophancy patterns? any anthropomorphizing escalation?") with a
  thumbs-up/down vote. A guardrail for heavy LLM use.
- **Community-group RSVP helper** — tiny channel that tracks open offers (who offered
  to help with what, who you offered to help) and surfaces the loops weekly. A
  follow-through layer for casual community commitments.
- **`!compress` command** — give it your remaining tasks for the day, it returns a
  reordered, time-boxed plan. Day-compression as a one-liner.
