---
name: xillion-status
description: Report where the xillion project currently stands and what to do next. Use when the user asks "where are we", "what's next", "continue", "what's pending", or starts a session wanting to resume work. Reads the task tracker, verifies it against actual repo state, and reports the next concrete task.
---

# Xillion status

Answer "where are we and what's next" **accurately** — which means verifying
the tracker against reality rather than just reciting it.

## Steps

1. **Read `docs/status/task-tracker.md`** — the header states the claimed current
   position (checkpoint, branch, last-updated date).

2. **Verify against reality.** Run these and compare:
   ```bash
   git status --short && git branch --show-current
   pytest tests/ -q 2>&1 | tail -3
   ```
   - Uncommitted work the tracker doesn't mention → the tracker is stale
   - Failing tests → say so prominently; that outranks any planned work
   - Branch mismatch → flag it

3. **Check what's blocked.** The tracker's "Blocked on you" table lists items
   only the user can unblock (credentials, strategy rules, CA opinion). Call
   these out — a blocked item silently waiting is worse than a known gap.

4. **Report concisely:**
   - Current checkpoint / pipeline stage, and whether it's genuinely where the
     tracker claims
   - **The single next concrete task**, not a menu of options
   - Anything blocked on the user, with what specifically is needed
   - Any discrepancy found between tracker and reality

## Rules

- **Trust the code over the tracker.** If `git status` or `pytest` contradicts
  the tracker, the tracker is wrong — say so and offer to correct it.
- Don't re-plan. The plan exists in the tracker; the job here is orientation,
  not redesign. Only propose changes if something is genuinely blocked or
  invalidated.
- Keep it short. Someone asking "where are we" wants a paragraph, not a
  document.
- If the tracker's "Last updated" is more than a few sessions stale relative
  to git history, flag that the update protocol has been skipped.
