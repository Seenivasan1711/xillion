# 08 — Testing Strategy

The point of testing this system is not "code coverage." It is **"the day you go live, nothing surprises you."**

## 1. Test pyramid for this product

```
                       ▲
                       │   Manual go-live drills (a few)
                       │
                       │   E2E browser tests (handful)
                       │
                       │   Integration tests (dozens)
                       │
                       │   Unit tests (hundreds)
                       ▼
```

But with one twist for trading: **paper-mode soak tests** sit alongside E2E. They simulate full trading sessions and are the most valuable insurance against real-money disasters.

## 2. Unit tests

Cover:
- Risk Manager: every gate (per-strategy, account, OPS, margin, sanity) tested in isolation
- Order state machine: every legal and illegal transition
- Plugin loader: malformed plugin → graceful skip + clear error
- Aggregator: ticks → bars under various edge cases (gaps, holidays, partial bars)
- Audit log: hash chain verifies on tamper
- Backtest engine: deterministic given (strategy, params, data, seed)
- Position math: long/short/partial fills/scale-in/scale-out

Tools: `pytest`, `pytest-asyncio`, `hypothesis` (property-based for state machines).

Coverage target: **≥ 90% on `algotrader/core/`**, lower elsewhere. Coverage of `brokers/` is integration territory.

## 3. Integration tests

Test the **wiring**:

- Strategy → ctx.buy() → Risk Manager → Execution Router → Backtest Broker → Order recorded → Strategy `on_order_update` called
- Paper Broker fills against canned tick stream
- Reconciliation detects manufactured drift
- Hot reload of a strategy preserves position state
- Kill switch fires through every layer

These run with an in-memory SQLite + a fake broker plugin that records calls.

## 4. End-to-end (E2E) tests

Browser-driven tests with **Playwright** covering critical flows:

- Login → 2FA → dashboard
- Add a strategy instance → run backtest → see results
- Switch strategy to paper → see simulated trades
- Click kill switch → confirm with 2FA → see all paused
- Audit log search shows the kill event

These are slow; run them on CI but not on every commit.

## 5. Paper-mode soak tests (the special one)

Run the **whole system** in paper mode against a recorded tick replay or a live test session, for hours. Validate:

- No memory leak
- No unhandled exceptions
- No slow queries piling up
- Reconciliation stays clean
- Audit log captures everything
- Performance (latencies) hold

A weekly automated soak run during market hours, results archived. **Required passing run before any v1 release tag.**

## 6. Backtest validation

Two specific checks that catch the most embarrassing bugs:

1. **No-lookahead test.** Every `ctx.history()` call inside `on_bar` must return only bars that closed before `bar.ts`. Add a test that asserts this on a recorded backtest run.
2. **Determinism test.** Run the same backtest twice → byte-identical metrics and trade list. (Random seeds where used must be fixed.)

## 7. Performance tests

- `pytest-benchmark` on hot paths: bar aggregator, risk gate, backtest loop
- Locust or k6 against API endpoints under realistic load (one user, but lots of WebSocket events)
- Memory profiling: `tracemalloc` snapshots at 1 / 60 / 360 minute marks during a soak run

## 8. Manual go-live drills

Not automated; do them before each major release.

| Drill | Pass criteria |
|---|---|
| Place a real ₹0 order (e.g., outside market hours, AMO with quantity 1) | Goes through, audit log clean |
| Place a real order during market with **smallest possible quantity** | Filled, position tracked, P&L correct vs Kite |
| Trigger kill switch with real open orders | All cancelled within 5 sec, audit clean |
| Pull network cable for 30 sec, then plug back | Bot reconnects, reconciliation detects no drift |
| Restart server with open positions | After boot, positions match broker, no spurious orders |
| Force broker auth failure (bad token) | Bot pauses live trading, alerts user, doesn't crash |
| Tomorrow morning (after Kite token expiry) | Auto-relogin succeeds, system is ready by 09:00 IST |

Document each drill's outcome in a release log.

## 9. Safety checklist before going live with a new strategy

Inside the product, the "Switch to Live" button is gated by these checks:

- [ ] Strategy has been backtested on at least 6 months of data
- [ ] Strategy has run in paper mode for at least 5 trading days
- [ ] Paper-mode P&L is within tolerance of backtest expectation (e.g., not catastrophically worse)
- [ ] Strategy's parameters and capital allocation are saved
- [ ] Risk limits are configured (daily loss cap, max position)
- [ ] Broker connection is healthy
- [ ] User completed 2FA confirmation

If any unchecked, the button is disabled with explanation.

## 10. CI matrix

Run on every PR:
- Lint (ruff), format (black), type-check (mypy), security (bandit, pip-audit)
- Unit tests + integration tests on Python 3.11 and 3.12
- DB compatibility: tests run on SQLite *and* Postgres
- Frontend: `pnpm test`, Playwright E2E (smoke subset only on PR; full suite on main)

Run nightly on main:
- Full Playwright E2E
- 30-minute paper-mode soak (recorded data)
- Backtest determinism check across 5 seed strategies
- Performance benchmarks (alert on regression > 20%)

Run weekly:
- 4-hour paper-mode soak during market hours
- DB migration round-trip test (apply all migrations on prod-shaped seed DB)

## 11. What we don't test

To be honest about scope:

- We don't fuzz-test against real broker APIs (would burn money)
- We don't simulate exchange-side outages beyond "broker disconnect"
- We don't have model-risk testing (i.e., is the strategy *actually* good) — that's the strategy author's job
- We don't load-test for thousands of users — single-user system

These are real gaps; they become real problems only at commercial scale.

## 12. Bug severity & response

| Severity | Definition | Response |
|---|---|---|
| Critical | Real money lost or at risk; bot misbehaves with live orders | Disable affected feature immediately; hotfix with priority |
| High | Risk control bypass possible (theoretical, not exploited) | Hotfix this week |
| Medium | Wrong UI, log noise, dev-mode glitch | Next release |
| Low | Cosmetic | Whenever |

Critical bugs trigger an automatic kill-switch fire by policy.
