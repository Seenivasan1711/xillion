---
doc_id: 14-TESTING
title: Testing Strategy and Acceptance Criteria
audience: QA, backend
version: 1.0
---

# 14 — TESTING & ACCEPTANCE

**In a trading system, a bug is not a defect report — it is a withdrawal.** Test coverage requirements are graded by blast radius.

---

## 14.1 Coverage requirements

| Module | Required | Rationale |
|---|---|---|
| **Risk engine** | **100% branch** | Untested branch = uncapped loss |
| **E05 execution + rollback** | **100% branch** | Naked-short scenario |
| **T03 trailing stop** | **100% branch** + property tests | Ratchet must never fail |
| **X02 square-off** | **100% branch** | Must work when all else fails |
| E03 sizing | 95% | Wrong size = wrong risk |
| E02 gate | 100% (one test per gate) | Fails closed |
| M01 reconciliation | 95% | State divergence detection |
| Broker adapters | 90% + contract tests | External boundary |
| Strategy plugins | 85% | Isolated blast radius |
| Reporting/analytics | 70% | Low blast radius |

---

## 14.2 Test layers

### Unit
Pure functions, no IO. Every risk check, every sizing branch, every trailing algorithm.

### Property-based (`hypothesis`)
```python
@given(price_series=st.lists(st.floats(100, 10000), min_size=2, max_size=1000),
       direction=st.sampled_from(["LONG", "SHORT"]))
def test_stop_never_loosens(price_series, direction):
    """The ratchet invariant. The single most important property in the system."""
    pos = make_position(direction)
    prev = pos.stop
    for p in price_series:
        pos = update_trailing_stop(pos, p)
        if direction == "LONG":
            assert pos.stop >= prev
        else:
            assert pos.stop <= prev
        prev = pos.stop

@given(order=order_strategy(), ctx=risk_context_strategy())
def test_risk_engine_never_approves_over_limit(order, ctx):
    d = validate_order(order, ctx)
    if d.approved:
        assert order.risk <= ctx.risk_budget - ctx.risk_used
        assert order.qty <= ctx.freeze_qty
        assert ctx.margin_available >= ctx.margin_required * 1.2
```

### Contract tests (broker adapters)
Same suite runs against every adapter — real sandbox and mock. Guarantees adapters are interchangeable.

### Integration
Full pipeline with a mock broker: signal → gate → size → construct → execute → verify → protect → monitor → exit → reconcile.

### Chaos
```
□ Kill Redis mid-order          → fail closed, no order placed
□ Kill Postgres mid-position    → position state recoverable from broker
□ Broker returns 500            → retry with backoff, then block
□ Broker returns duplicate ack  → idempotency prevents double position
□ Network partition mid-submit  → reconciliation finds truth, no duplicate
□ Clock jumps 5 minutes         → halt
□ Kill main process w/ position open → watchdog flattens within 120s
□ MT5 terminal crash            → local watchdog restarts, position protected
□ Data feed silence 60s         → flatten per circuit breaker
□ Disk full                     → alert, degrade gracefully, do not corrupt
```

### Scenario tests — real market situations
```
□ Gap through stop              → exits at next available price, loss recorded correctly
□ Circuit limit hit             → orders rejected gracefully
□ Illiquid leg (bid=0)          → P0 alert, no order
□ Partial fill 60%              → position at 60%, protective orders RESIZED
□ Leg 1 fills, leg 2 rejects    → rollback, no naked short
□ Short fills, long hedge fails → FORCE UNWIND within 5s
□ Expiry-day gamma spike        → stops honoured, flat by 14:00
□ Holiday-shifted expiry        → P02 resolves to previous trading day
□ Lot size changes overnight    → P06 halts trading, alerts
□ Prop firm DD hit 90%          → new entries blocked
□ Prop firm DD hit 100%         → flatten + halt
```

---

## 14.3 Backtest engine validation

**The backtest engine itself must be tested, or it will lie to you confidently.**

```
□ Reproduce 10 manually hand-calculated trades EXACTLY (to the rupee)
□ Cost model verified against a real broker contract note
□ Fills occur at the unfavourable side of the recorded spread, never mid
□ Stops fill at next open, not trigger price (gap modelling)
□ Multi-leg costs charged per leg, both directions
□ Known-losing strategy produces a loss (sanity — no accidental look-ahead)
□ Look-ahead bias test: shuffle future data → results must degrade to noise
□ Same strategy code runs in backtest and live (no divergent code path)
```

**The look-ahead test is the one people skip and the one that matters most.** If shuffling future bars does not destroy your backtest's edge, your backtest is reading the future somewhere.

---

## 14.4 Pre-live checklist

Before `mode: live`:

```
COMPLIANCE
□ Static IP whitelisted and verified with broker
□ OAuth + 2FA flow works end to end
□ OPS throttle verified: 20 orders in 1s → halts
□ Audit logging captures every order and risk decision

SAFETY
□ Kill switch tested from phone (<5s)
□ File sentinel kill switch works with app wedged
□ Watchdog flattens on main-process death
□ X02 works with app stopped
□ All circuit breakers fire at configured thresholds
□ E05 rollback: force-unwind verified

CORRECTNESS
□ 30+ paper trades, zero state divergence
□ M01 reconciles clean 5 consecutive days
□ Lot size, expiry, costs verified against live exchange data
□ Sizing verified by hand for 5 scenarios incl. lots==0

OPERATIONS
□ Backups running and RESTORE-TESTED
□ Alerts reach the phone; P0 escalates
□ Grafana dashboards live
□ Runbook written (15) and walked through
□ Broker's mobile app installed and logged in (manual fallback)

BUSINESS
□ Strategy passes KB 09 backtest criteria incl. 2026-YTD split
□ wr_margin > 0 on paper results
□ Max loss per trade confirmed in rupees, and it is an amount you accept losing
```

---

## 14.5 Per-phase acceptance

Referenced in `13-IMPLEMENTATION-ROADMAP.md`. **A gate item is binary — no partial credit, no "mostly works."**

---

## 14.6 Ongoing testing in production

```
Daily     smoke test in paper before market open
Weekly    restore-test a backup; verify data integrity
Monthly   live-fire kill switch drill in paper mode
Monthly   reconcile a full month against broker statements by hand
Quarterly full chaos suite re-run
```
