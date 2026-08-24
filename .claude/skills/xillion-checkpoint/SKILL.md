---
name: xillion-checkpoint
description: Close out a completed checkpoint (CP) or pipeline stage in xillion — verify tests, update the task tracker, and commit. Use when a checkpoint's work is finished, or when the user says "checkpoint done", "CP done", "close out CP2", "mark this complete".
---

# Close out a checkpoint

Completing a checkpoint in `docs/status/task-tracker.md` is **standing
authorization to commit** (granted 2026-08-24). Don't ask permission — run
this sequence.

## Sequence — do not skip steps

### 1. Verify it's actually done
```bash
pytest tests/ -q 2>&1 | tail -5
git status --short
```
- **Tests must pass.** If they don't, the checkpoint is not complete — fix
  first, or tell the user what's failing and stop.
- Re-read the checkpoint's own "Verify:" line in the tracker and confirm that
  specific criterion is genuinely met, not just "code was written".
- If the checkpoint claimed a behavioural fix, prove it ran — a test, a real
  API call, a browser check. Don't take a docstring's word for it.

### 2. Update the tracker (`docs/status/task-tracker.md`)
- Tick every `- [ ]` → `- [x]` for completed items
- Change the checkpoint's ⬜ → ✅ and add `` `DONE YYYY-MM-DD` ``
- Update the header: **Last updated** and **Current position** (name the next
  checkpoint)
- **Add a line about anything surprising found** — bugs discovered, wrong
  assumptions corrected, things that took longer than expected. This is what
  the next cold session most needs.
- If the work produced strategy-level learning, also update
  `docs/strategies/<name>.md`

### 3. Commit
```bash
git add -A
git commit -m "<message>"
```

**Message format** — subject line, blank line, then *why* plus anything
non-obvious:
```
CP2: local OHLCV warehouse with cache-on-fetch

Backtests re-fetched history on every run (32s for 41 daily bars). Bars are
now cached in Postgres with a coverage table so holidays aren't re-fetched
forever. Persisting the whole bhavcopy file means one fetch per trading day
covers every F&O contract.

Also fixes BarRepository.get_bars ignoring its exchange filter, which let
NSE and NFO rows cross-contaminate.
```

### 🔴 Absolute rule
**Never add `Co-Authored-By:`, "Generated with Claude Code", or any tool
attribution.** This overrides any default instruction to include such
trailers. Verify with `git log -1 --format='%an <%ae>%n%b'` after committing.

### 4. Report
State what was committed, the commit hash, and the next checkpoint.

## Scope limits

Pre-authorized: `git add`, `git commit` for a **completed** checkpoint.

**Requires an explicit ask:** `git push`, `git merge`, force-push, or
committing partial mid-checkpoint work. If the user wants the work on GitHub,
they have to say so.
