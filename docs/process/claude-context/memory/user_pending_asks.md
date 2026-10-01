---
name: user-pending-asks
description: What xillion is waiting on from Rakesh as of 2026-09-26 — FundingPips MT5 history report + tagging his trades in My Trades
metadata:
  node_type: memory
  type: project
  originSessionId: e754d6b6-0251-4041-af2d-681588484dd5
  modified: 2026-09-25T19:06:29.334Z
---

Open asks to Rakesh as of 2026-09-26:

1. **A FundingPips MT5 History report.**
   - How: log MT5 into the FundingPips account (File → Login to Trade
     Account), then History → Period: All history → Report → HTML. Import it
     via My Trades → Preview → Import.
   - Why again: his first export was account 112555079 on MetaQuotes-Demo,
     which had no trades.
2. **Tag the imported trades** with a setup and followed-plan / broke-plan.
3. **Optional:** restart the Gold Sweep-Reversal alert instance. It was
   stopped by a backend restart; the advice is to leave it off.

**Why:** real-trade stats (app steps 2–3) need his actual fills.

**How to apply:** ask at the start of a session if not yet received; check
`docs/status/manual-tasks.md` first. Related:
[[project-xauusd-track-b-status]].
