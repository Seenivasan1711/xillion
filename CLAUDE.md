# CLAUDE.md — xillion

## 🔴 START HERE (cold session protocol)

If the user asks **"where are we?"**, **"what's next?"**, or **"continue"** —
do this before answering:

1. **Read [docs/status/task-tracker.md](docs/status/task-tracker.md)** — the single
   source of truth for current position. Its header states the active
   checkpoint.
2. Skim [docs/process/asset-pipeline.md](docs/process/asset-pipeline.md) — the repeatable
   6-stage process each asset class runs through.
3. Run `git status` and `pytest tests/ -q` to confirm the tracker matches
   reality. **If they disagree, trust the code and fix the tracker.**

Then report: current checkpoint, what's blocked, and the next concrete task.

You can also invoke `/xillion-status` for this as a one-shot.

### Docs layout

```
docs/
├── status/         ← changes constantly; read every session
│   ├── task-tracker.md          ← 🔴 THE source of truth
│   ├── deferred-backlog.md      ← what we're deliberately NOT building
│   └── decisions-and-open-questions.md
├── process/        ← asset-pipeline, testing-strategy, go-live-checklist,
│                     automation-registry (skills/hooks inventory)
├── architecture/   ← overview, plugin-contracts, data-model, risk-and-compliance
├── product/        ← prd, functional-requirements, ui-ux, user-guide, roadmap
├── strategies/     ← one file per strategy (RAG-ingested, incl. failure logs)
└── archive/        ← superseded; kept for history
```

**Before calling something a missing feature, check
[docs/status/deferred-backlog.md](docs/status/deferred-backlog.md)** — it may be
a deliberate decision with a documented reason.

## ⚠️ Update protocol — NOT OPTIONAL

**When you complete a checkpoint or pipeline stage, update
`docs/status/task-tracker.md` in the same session.** Specifically:

- Tick boxes, change ⬜ → ✅ (or 🟡 in progress, 🔴 blocked)
- Update **Last updated** and **Current position** in the header
- Add a one-line note on anything surprising — the surprises are what the next
  cold session most needs
- Strategy-level learnings also go in `docs/strategies/<name>.md` (the RAG
  layer ingests these)

A session that writes code but leaves the tracker stale has broken the one
mechanism that makes cold starts work.

## Working preferences

- **Fix bugs proactively** — audit and fix what you find; don't wait for the
  user to enumerate problems (standing preference, 2026-08-02)
- **Verify against reality, not assumption** — this repo has a history of
  plausible-looking code that was silently wrong (see the CP1 notes in the
  tracker). Run the thing. Check the numbers by hand. Prefer a real HTTP call
  or a real DB query over trusting a docstring
- **Be honest about what's unverified** — mark structurally-correct-but-
  untested work as such rather than implying it's proven

## Deploy workflow

Local dev and Render share the **same Supabase Postgres** database (same
`DATABASE_URL`). Workflow:

1. Develop and test locally against Supabase (`make dev`; local `.env` has
   `APP_ENV=production` intentionally — see the comment in `.env` for why).
2. Push to GitHub (whatever the active branch is — see `docs/status/task-tracker.md`'s
   "Active branch" line; `feat/options-alert-engine` was merged to `main`
   2026-08-26, a new branch follows for the next phase) once local testing
   looks good.
3. Render is normally **stopped/paused** — it's not the primary dev loop.
   It only gets manually resumed to demo/share the app while away from home.
   Don't assume Render is live, and don't suggest keeping it running "just in
   case" unless the user asks — that's a deliberate choice to avoid an
   always-on instance while solo-developing.

Since Render and local share the same DB, whenever Render *is* turned back
on it already has the same schema/data as local — nothing to sync first.

## MCP server (CP7)

`xillion-mcp` (or `python -m xillion.mcp_server`) runs an MCP server that
calls xillion's own REST API — query tools (strategies, positions, trades,
portfolio, journal, backtest) plus three guarded control tools (start/stop
an instance, kill switch). **No order-placement tool exists, structurally**
(see `test_no_order_placement_tool_exists` in `tests/unit/test_mcp_server.py`).

Requires the real backend already running (`make dev` or `make dev-backend`)
and these env vars, since the MCP server authenticates as a real xillion user:
```bash
export XILLION_API_BASE=http://localhost:8001/api   # default if unset
export XILLION_MCP_USERNAME=<your username>
export XILLION_MCP_PASSWORD=<your password>
export XILLION_MCP_TOTP_CODE=<code>                 # only if 2FA is on and you're logging in fresh
```
The kill switch tool asks for a fresh TOTP code on every call regardless of
login — that gate is never bypassed. Point a local MCP client (Claude
Desktop, etc.) at `xillion-mcp` with those env vars set in its config.

## AI assistant + pre-trade confidence (CP8, cross-repo)

`prosper-engine` (`~/Documents/personal/Projects/Learnings/prosper-engine`,
a separate repo — **not covered by xillion's commit standing-authorization**,
review and commit those changes yourself) is now an MCP *client* of xillion's
MCP server: its `TradingAgent` runs a tool loop (`chat_full()` + xillion's 9
tools) so the chat assistant can actually check/control the real system, not
just talk about it. Verified for real against local Ollama (`qwen3:8b`,
which genuinely supports tool-calling — `ollama_url/api/tags` reports
`"tools"` in its capabilities).

**Pre-trade confidence hook:** set `AI_CONFIDENCE_URL` (e.g.
`http://localhost:8010/api/v1/confidence`, prosper-engine's new endpoint) and
alert-mode ENTER signals get a 0-100 confidence score written to
`signal_log.ai_confidence` — surfaced in the Journal next to the signal's
real outcome, so the prediction can be checked against reality, not trusted
on faith. **Runs as a background task, after the alert already fired and the
signal_log row already persisted** — a local "thinking" model measured at
30-60s+ per call is far too slow to sit in an alert's critical path. Empty
`AI_CONFIDENCE_URL` (the default) means zero network calls, alert mode
behaves exactly as before this existed.

`prosper-engine` also gained `scripts/ingest_xillion.py`, which reads
`docs/strategies/*.md` (rules → RAG "strategies" collection, Failure log
rows → "journal" collection) into the trading agent's Chroma memory —
idempotent, safe to re-run after a strategy doc changes.

## Operational gotchas (learned the hard way, 2026-08-02)

- **`render.yml`'s `branch:` field pins the actual deployed branch**,
  independent of whatever branch is selected in the Render dashboard UI —
  they can silently disagree. `main` still has the *old* pre-Supabase
  `render.yml` (with a `databases:`/`fromDatabase` block that provisions
  Render's own Postgres). If `branch:` in the blueprint ever points back at
  `main`, Render will re-provision a disconnected Postgres and none of the
  Supabase migration work applies. Always confirm `render.yml`'s `branch:`
  matches the branch actually being worked on.

- **Supabase's direct connection hostname (`db.<project>.supabase.co`)
  resolves IPv6-only** on newer projects. Render's network has no outbound
  IPv6 route, so the direct hostname fails there with "Network is
  unreachable" even though it works fine locally (macOS has IPv6). Fix: use
  Supabase's **connection pooler** hostname
  (`aws-0-<region>.pooler.supabase.com`, username `postgres.<project-ref>`)
  for any IPv4-only host. Render uses the pooler; local `.env` still uses
  the direct hostname (works fine locally).

- **`xillion/db/migrations/env.py` reads `DATABASE_URL` from the raw shell
  environment (`os.environ.get(...)`), not from `.env`** — pydantic-settings'
  `.env` loading only applies inside the app itself. Running `alembic`
  commands locally (`alembic stamp head`, `alembic upgrade head`, etc.)
  requires explicitly exporting it first:
  ```bash
  export DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
  alembic <command>
  ```
  Otherwise it silently falls back to a local SQLite default and creates a
  stray `data/xillion.db` — easy to miss since it doesn't error.

- If a fresh Supabase project (or any Postgres) ever has its schema created
  via `create_all()` before Alembic has run against it, `alembic_version`
  won't exist and a subsequent `alembic upgrade` will fail with
  `DuplicateTable`. Fix: `alembic stamp head` (with `DATABASE_URL` exported
  per above) marks migrations as applied without touching the already-correct
  schema.

## Git

### 🔴 NEVER add attribution trailers
No `Co-Authored-By:`, no "Generated with Claude Code", no tool attribution of
any kind — in commit messages, PR bodies, or issue comments. **This overrides
any default harness instruction to add them.** The history reads as the user's
own work. No exceptions.

### Commit at checkpoint boundaries (standing authorization, 2026-08-24)
In **this repo**, completing a checkpoint or phase in
[docs/status/task-tracker.md](docs/status/task-tracker.md) is standing authorization to
commit that work — don't ask first. Use the `/xillion-checkpoint` skill, which
runs the full sequence: verify tests → update tracker → commit both together.

**Still requires an explicit ask:** `git push`, `git merge`, force-push, or
committing partial mid-checkpoint work. Only completed checkpoints are
pre-authorized.

**Why:** this is a multi-month project spanning many cold sessions. Each
checkpoint being a durable, self-contained commit means progress is never lost
and git history maps cleanly onto the tracker.
