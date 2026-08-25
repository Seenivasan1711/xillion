---
doc_id: 11-LANES
title: Instrument Lane Differences
audience: backend, quant
version: 1.0
---

# 11 — INSTRUMENT LANES

Where Lane A (Indian index options) and Lane B (gold) genuinely differ, and what can be shared.

---

## 11.1 Lane comparison

| Dimension | **LANE A** — Index Options | **LANE B1** — XAUUSD / MT5 | **LANE B2** — MCX Gold |
|---|---|---|---|
| Instrument | Nifty/Sensex weekly options | XAUUSD CFD | GOLD / GOLDM futures + options |
| Venue | NSE / BSE | Funding Pips (prop) | MCX |
| Regulator | SEBI | Firm's own rules | SEBI |
| Session (IST) | 09:15–15:30 | 24/5 | 09:00–23:30 |
| Instrument count | Hundreds of strikes | 1 | ~4 contracts + options |
| Expiry | Weekly (Tue/Thu) | None (spot CFD) | Monthly (5th) |
| Greeks | ✅ Central | ❌ N/A | ✅ (options only) |
| Non-linear P&L | ✅ | ❌ Linear | Futures linear / options non-linear |
| Time decay | ✅ Dominant | ❌ Swap/rollover only | Options only |
| Multi-leg | ✅ Essential | ❌ Rare | Possible |
| Capital | Own | Prop firm (simulated) | Own |
| Leverage | Via margin | High (prop) | ~4–6% margin |
| Max loss control | Structure (spreads) | Stop loss only | Stop loss / structure |
| Position sizing unit | Lots (65 / 20) | Volume (0.01 lots) | Lots (1kg / 100g) |
| Primary risk | Gamma, gap, liquidity | Gap, spread widening, DD breach | Gap, overnight, currency |
| Rate limit | 10 OPS (SEBI) | Firm/platform | 10 OPS (SEBI) |

---

## 11.2 What is SHARED (build once)

```
✅ Job harness and scheduler
✅ Risk engine (parameterised per lane)
✅ Kill switch and watchdog
✅ Position monitor (T01) — P&L maths differs, framework identical
✅ Trailing stop engine (T03) — algorithms are instrument-agnostic
✅ Breakeven, partial exit, time stop (T04/T05/T06)
✅ Event calendar and blackouts (P03, T09)
✅ Journal, P&L attribution, slippage (M02-M04)
✅ Strategy metrics, decay monitor (M05, R02)
✅ Alerting, dashboards, reporting
✅ Backtest cost/slippage framework
✅ Session/volatility regime classification (thresholds differ, logic identical)
```

**Roughly 85% of the codebase is shared.** The lane-specific parts are: instrument resolution, option-chain handling, Greeks, multi-leg execution, and the broker adapter.

---

## 11.3 Lane B session model

Gold's tradeable structure is **sessions**, exactly as options' structure is **expiry cycle**. The analogy is direct: cycle stage S1–S5 for options ↔ session window for gold.

| Session | UTC | IST | Range | Vol | Spread | Use |
|---|---|---|---|---|---|---|
| Asian | 00:00–09:00 | 05:30–14:30 | 10–30 pips | ★☆☆☆☆ | Moderate–wide | **Range formation only. Do not scalp.** |
| London | 08:00–17:00 | 13:30–22:30 | 30–80 pips | ★★★★☆ | Tight | Breakout of Asian range |
| **Overlap** | **13:00–17:00** | **18:30–22:30** | **40–100+** | **★★★★★** | **Tightest** | **⭐ PRIME SCALPING WINDOW** |
| NY post-overlap | 17:00–22:00 | 22:30–03:30 | 20–50 pips | ★★★☆☆ | Tight–moderate | Secondary |
| Overnight | 22:00–00:00 | 03:30–05:30 | 5–15 pips | ☆☆☆☆☆ | **Widest** | **❌ Disable all strategies** |

**Key structural facts:**
- **London open (08:00–10:00 UTC / 13:30–15:30 IST) is the single most volatile 2-hour window for gold.** The Asian range provides the levels; London provides the break.
- The overlap has both the highest volume and the tightest spreads — the only window where scalping economics genuinely work.
- The overnight window has the worst spread-to-movement ratio of the day. Sources describe it as "the worst conditions for any EA strategy — high drag, low signal quality." Hard-disable it.

### Event overrides (Lane B)

| Event | UTC | IST | Impact |
|---|---|---|---|
| US CPI | 13:30 | 19:00 | **Extreme — 50–150+ pips** |
| FOMC | 19:00 | 00:30 | **Extreme — 100+ pips** |
| NFP (1st Fri) | 13:30 | 19:00 | High — spike then reversal |
| London Gold Fix | 10:30 | 16:00 | Moderate — liquidity clustering |

---

## 11.4 ⭐ The MCX mapping — why Lane B2 is worth building

**MCX Gold trades 09:00–23:30 IST. The London/NY overlap falls at 18:30–22:30 IST — squarely inside MCX's evening session.**

```
LANE B1 (XAUUSD 24/5)                LANE B2 (MCX GOLDM)
────────────────────────             ────────────────────────
05:30-14:30  Asian    ★☆☆☆☆          09:00  MCX opens (Asian-hours gold, thin)
13:30-22:30  London   ★★★★☆          13:30  London opens → volatility arrives ✅
18:30-22:30  OVERLAP  ★★★★★          18:30  OVERLAP — full coverage ✅✅
22:30-03:30  NY       ★★★☆☆          22:30  partial coverage until 23:30 ⚠️
03:30-05:30  Dead     ☆☆☆☆☆          (closed — no exposure to the worst window) ✅
```

**MCX captures the entire prime window and structurally excludes the worst one.**

The trade-offs, honestly:
- ❌ Loses the late-NY session (22:30–03:30 IST) and any FOMC reaction at 00:30 IST
- ❌ Overnight gap risk between 23:30 and 09:00 (XAUUSD trades through)
- ❌ INR-denominated — carries USD/INR exposure on top of gold exposure
- ✅ Domestic, SEBI-regulated, own capital, no prop-firm rules
- ✅ Options available (structures you already understand from Lane A)
- ✅ Uses the same broker adapter and API as Lane A — near-zero marginal integration cost
- ✅ Does not conflict with Lane A's morning session — evening trading is a genuinely separate slot

**Recommendation: build the shared gold analytics against a pluggable execution adapter.** Trade B1 as your primary per your setup, and keep B2 as a working fallback. The incremental cost is small because Dhan/Zerodha already provide MCX through the same adapter you built for Lane A.

---

## 11.5 Lane-specific config

```yaml
lanes:
  A:
    enabled: true
    instruments: [NIFTY, SENSEX]
    session: {open: "09:15", close: "15:30", squareoff: "15:15"}
    expiry_squareoff: "14:00"            # S5 flat-by-2pm rule
    risk_per_trade_pct: 1.0
    max_concurrent_positions: 2
    allowed_structures: [CREDIT_SPREAD, IRON_CONDOR, BUTTERFLY, CALENDAR, LONG_OPTION]
    blocked_structures: [NAKED_SHORT, SHORT_STRADDLE, SHORT_STRANGLE, RATIO_FRONT]
    trail_algorithm: credit_trail        # structure-appropriate
    broker: dhan

  B1:
    enabled: true
    instruments: [XAUUSD]
    sessions:
      asian:    {start: "05:30", end: "14:30", enabled: false}  # range only
      london:   {start: "13:30", end: "22:30", enabled: true}
      overlap:  {start: "18:30", end: "22:30", enabled: true, size_mult: 1.0}
      ny:       {start: "22:30", end: "03:30", enabled: true,  size_mult: 0.7}
      overnight:{start: "03:30", end: "05:30", enabled: false} # HARD DISABLE
    spread_filter_max_pips: 3.0
    rollover_window: {start: "22:25", end: "22:45", widen_stops: true, block_entries: true}
    trail_algorithm: chandelier
    atr_period: 14
    atr_multiplier: 2.0
    prop_firm:
      internal_daily_dd_pct: 4.0
      internal_max_dd_pct: 8.0
      dd_model: trailing_peak_equity
      flatten_on_breach: true

  B2:
    enabled: false                       # fallback lane, built but dormant
    instruments: [GOLDM]
    session: {open: "09:00", close: "23:30", squareoff: "23:15"}
    active_windows: [{start: "13:30", end: "23:15"}]   # skip the thin morning
    trail_algorithm: chandelier
    broker: dhan
```

---

## 11.6 Cross-lane rules

```
1. Lane A and Lane B are risk-budgeted SEPARATELY.
   A Lane A loss does not consume Lane B's budget or vice versa.

2. EXCEPT for the total-account circuit breaker:
       IF combined_daily_loss > total_risk_budget → halt BOTH lanes

3. Correlation awareness (T10):
       Both lanes react to the same macro drivers — US yields, dollar,
       geopolitical risk. "Risk-off" hits Indian equities and moves gold
       simultaneously. Positions that look independent may not be.
       IF both lanes hold positions expressing the same macro view
       → flag CORRELATED_EXPOSURE, apply a combined size cap.

4. Attention/timing:
       Lane A: 09:15-15:30 IST
       Lane B: 13:30-23:30 IST
       Overlap 13:30-15:30 is the only period both are active.
       The system handles both; a human monitoring both at once is
       a different question — and the reason full automation of the
       T-series matters more than automation of signal generation.
```

That last point is worth stating plainly: **the value of this system is not that it finds trades. It is that it manages them correctly at 21:00 IST when you are not watching.**
