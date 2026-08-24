---
name: xillion-verify
description: Verify a claim about xillion against reality instead of assuming — run the code, query the DB, hit the API, hand-check the math. Use before trusting any backtest number, after implementing a fix, when a metric looks surprising, or when the user asks "is this actually working / correct?"
---

# Verify against reality

This repo's history is full of **plausible-looking code that was silently
wrong**: equity curves that never moved, shorts that vanished, P&L off by the
lot size (65×), a reload endpoint that returned 200 while writing nothing, a
backtest showing 0 trades with no error. None of these threw exceptions —
they were only caught by checking against an independent source of truth.

**The rule: a claim is unverified until a second, independent path confirms it.**

## Verification ladder — use the strongest rung that applies

1. **Hand-check the math.** For any P&L/metric claim, compute a small sample
   manually (5 trades, one equity path). This is what caught the 65× bug and
   the flat-equity bug. `FeeConfig.zero()` exists to make exact arithmetic
   assertable.

2. **Query the real database.** For "X was persisted" claims:
   ```bash
   export DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
   # then query via python + xillion.db.session, or psql
   ```
   The strategy_class sync bug returned 200 while the table stayed empty —
   only the DB query exposed it.

3. **Hit the real API.** `curl` the endpoint; check status *and* body.
   Log in first if needed (session cookie via `/api/auth/login`).

4. **Drive the real UI.** Browser tools: click the flow, then check network
   requests *and* console errors. A 200 with a console error is still broken.

5. **Cross-validate against an external source.** Data-provider claims get
   checked against the provider's actual file/API (the NSE bhavcopy provider
   was validated row-by-row against the real ZIP; DhanHQ's securityId against
   NSE's own instrument token).

6. **Write the regression test.** Once verified, pin it: the bug class that
   happened once will happen again. `tests/unit/test_backtest_equity.py` is
   the pattern — each test names the bug it pins in its docstring.

## Honesty rules

- Distinguish **verified** ("ran it, saw X") from **structurally correct but
  untested** ("code follows the right pattern; no credentials to test live").
  Both are fine; conflating them is not. The Kite and DhanHQ providers are
  examples of the honest-caveat pattern — copy it.
- If verification fails, the finding outranks whatever was planned. Stop and
  report before building on sand.
- Never mark a tracker checkbox based on "the code was written." The
  checkpoint's own "Verify:" line states the proof required.
