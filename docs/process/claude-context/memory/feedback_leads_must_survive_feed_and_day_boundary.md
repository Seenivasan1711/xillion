---
name: leads-must-survive-feed-and-day-boundary
description: Before calling any xillion backtest result a "lead", re-run it on the other feed and check zero-trade months — three leads in one day were artifacts
metadata:
  type: feedback
---

On 2026-09-25, three XAUUSD "leads" collapsed:
- S07 +$412 came from Dukascopy's missing minutes.
- S09 +$1,356 came from UTC-midnight "previous day" levels.
- S08 +$590 came from a stuck state machine; whole months had zero trades.

**Why:** Rakesh asked "recheck whether this backtesting happening correct
or not". He wants results he can trust before trading them.

**How to apply:** before reporting a positive result, check all of these:
- re-run it on the other feed (`RESEARCH_DATA_SOURCE`);
- check the monthly trade counts, where zero-trade months mean a stuck state;
- attribute the result to the rule, not an artifact.

Report it as unverified until those checks pass. Related:
[[project-xauusd-track-b-status]].
