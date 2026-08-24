# Automation registry

The durable inventory of every skill, hook, and standing CLAUDE.md rule in this
repo — what it's for, and why it exists. Kept current by
[xillion-tooling](../../.claude/skills/xillion-tooling/SKILL.md): built the moment
a task recurs a third time, retired the moment its phase ends.

**Last updated:** 2026-08-24

---

## Skills (`.claude/skills/`)

| Skill | Fires on | Why it exists |
|---|---|---|
| `xillion-status` | "where are we", "what's next", session resume | Cold sessions need current position without re-deriving it from git log |
| `xillion-checkpoint` | "CP done", "checkpoint complete" | Standardises verify → tracker update → commit so no checkpoint is half-closed |
| `xillion-new-strategy` | user brings strategy rules for any asset | Enforces Stage-1-before-code and the doc-before-code order every time |
| `xillion-verify` | any claim about correctness/persistence/metrics | This repo has a real history of plausible-looking wrong code (flat equity, 65× lot bug, silent 0-trade backtests) |
| `xillion-tooling` | 3rd repetition, repeated correction, "automate this" | Meta-skill — this file's own maintainer |

## Hooks (`.claude/hooks/`, wired in `.claude/settings.json`)

| Hook | Event | Blocks | Why |
|---|---|---|---|
| `session-start.sh` | SessionStart | — (informational) | Prints tracker header + uncommitted-file count so orientation is automatic |
| `bash-guard.sh` | PreToolUse(Bash) | `alembic` without `DATABASE_URL`; `git commit` with a >5MB staged file | Both failure modes happened for real and neither errors on its own — a stray SQLite stamp, a near-committed 32MB CSV |
| `tracker-guard.sh` | Stop | Ending the turn with code changed but tracker untouched and not dated today | The whole cold-start design depends on the tracker being current; this is the enforcement mechanism, not just a written rule |

## CLAUDE.md standing rules

| Rule | Why |
|---|---|
| 🔴 Cold-start protocol (read tracker → skim pipeline → verify with git+pytest) | Every session should reach "what's next" the same way, without re-asking |
| ⚠️ Update tracker in the same session a checkpoint completes | Non-optional — stated once, enforced by `tracker-guard.sh` |
| Fix bugs proactively, don't wait for a bug list | Standing preference, 2026-08-02 |
| Verify against reality, not assumption | Standing preference — see xillion-verify |
| 🔴 Never add commit/PR attribution trailers | Absolute, no exceptions, any repo |
| Commit at checkpoint boundaries is standing authorization | 2026-08-24 — push/merge/partial-work still need an explicit ask |

---

## Candidate watchlist

Things that looked repeatable but haven't hit 3 occurrences yet, or are real
future-repeats that haven't started. **Tally here instead of re-deciding each
time.** When a count reaches 3 (or a known future count makes the case on its
own), build it under `xillion-tooling` in the next session that touches it.

| Candidate | Signal so far | Count | Build when |
|---|---|---|---|
| `/xillion-add-provider` | NSE bhavcopy, Zerodha Kite, DhanHQ — same shape each time (ABC impl, `credential_fields`, plugin_sync) | 3 (built retroactively as pattern, not yet extracted as skill) | Next new provider (TrueData / TradingView) — extract then |
| `/xillion-advance-stage` | Asset pipeline (S1→S6) will run once per asset × 6 assets | 0 runs yet, but count is known in advance | Before starting the 2nd asset's pipeline (gold, per user's stated order) — 1st run (options) is still defining the steps |
| `/xillion-backfill` | CP3 backfill CLI is planned but not built | 0 | When CP3 lands and a second data source needs the same backfill treatment |
| `/xillion-verify-ui` | Browser-driven UI verification loop, run ~8× this session by hand | 8 (pre-dates this registry) | **Ready to build now** — see below |
| `/xillion-dev` | Stray dev-server process cleanup needed repeatedly | Several, informal | Next time a stray process blocks a port — capture the exact kill sequence then |

### Ready to build next session
`/xillion-verify-ui` already has enough repetitions (informal count: 8) to
justify building on sight next time a UI change needs browser verification —
don't wait to re-ask, just build it per Step 1–4 of `xillion-tooling`.

---

## Retired

None yet. When a phase-specific skill's phase ends (e.g. a backfill skill
after the one-time historical backfill is done), move its row here with the
retirement date and reason, then delete the file.
