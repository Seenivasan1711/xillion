---
name: project-xauusd-track-b-status
description: "xillion state 2026-10-01: research done (negative), ML filter failed, My Trades + FundingPips limits panel built; moving to a new machine, all pushed"
metadata:
  type: project
---

As of 2026-10-01, everything is on `feat/track-b-pipelines`, **pushed to
origin**, and not merged to main. Rakesh is moving to a new laptop (the old
one returns to his company).

- **XAUUSD research:** finished with a negative verdict (doc 14). The ML
  meta-labeling filter also failed (doc 15). The holdout (2025-07→) is unused.
- **App work done:**
  - My Trades: MT5 History-report import, manual trades, tags, per-setup
    stats.
  - FundingPips limits panel: closed trades only, with Telegram warnings on
    a level change.
- **Next (optional):** level alerts. Otherwise this is a pause until real
  FundingPips trades are imported.
- **New-machine steps:** `docs/process/new-machine-setup.md` §7–§11.
  Claude context is snapshotted in `docs/process/claude-context/`.

**Why:** cold sessions on the new machine must resume from here.

**How to apply:** read the ▶️▶️ COLD START block at the top of
`docs/status/task-tracker.md`. See [[user-pending-asks]] and
[[user-direction-xauusd-forex-track-b]].
