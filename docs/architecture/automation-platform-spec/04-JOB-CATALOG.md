---
doc_id: 04-JOB-CATALOG
title: Master Job Catalog
audience: everyone
version: 1.0
date: 2026-08-24
---

# 04 — MASTER JOB CATALOG

**52 jobs across 8 phases.** This is the index; full specs are in `05`–`09` and `10`.

Legend — **Lane**: A = options, B = gold, ● = both · **Phase**: implementation phase from `13` · **Crit**: P0 = capital-protecting, P1 = core, P2 = valuable, P3 = nice-to-have

---

## P — PRE-MARKET (10 jobs)

| ID | Job | Lane | Schedule (IST) | Crit | Phase |
|---|---|---|---|---|---|
| P01 | System Health & Auth Refresh | ● | 08:00, then hourly | **P0** | 1 |
| P02 | Market Calendar & Holiday Check | ● | 08:05 | P1 | 1 |
| P03 | Economic Event Calendar Ingest | ● | 08:10 | P1 | 2 |
| P04 | Overnight & Global Cues Scan | ● | 08:30 | P2 | 3 |
| P05 | Volatility Regime Classification | ● | 08:45 | P1 | 2 |
| P06 | Instrument & Expiry Resolver | A | 08:50 | **P0** | 1 |
| P07 | Capital & Margin Readiness | ● | 08:55 | **P0** | 1 |
| P08 | Strategy Arming / Selection | ● | 09:00 | P1 | 2 |
| P09 | Watchlist & Strike Shortlist Build | A | 09:05 | P1 | 2 |
| P10 | Pre-Market Brief Generation | ● | 09:10 | P2 | 3 |

## O — MARKET OPEN (3 jobs)

| ID | Job | Lane | Schedule | Crit | Phase |
|---|---|---|---|---|---|
| O01 | Opening Range Capture | ● | 09:15–09:45 streaming | P1 | 2 |
| O02 | Open Regime Confirmation | ● | 09:45 | P1 | 2 |
| O03 | Gap Classification & Veto | ● | 09:16 | P1 | 2 |

## E — ENTRY (7 jobs)

| ID | Job | Lane | Trigger | Crit | Phase |
|---|---|---|---|---|---|
| E01 | Signal Generation | ● | Event: bar close | P1 | 2 |
| E02 | **Pre-Entry Gate** | ● | Event: signal | **P0** | 1 |
| E03 | Position Sizing Calculator | ● | Event: gate pass | **P0** | 1 |
| E04 | Order Construction & Validation | ● | Event: sized | **P0** | 1 |
| E05 | Order Execution | ● | Event: validated | **P0** | 1 |
| E06 | **Fill Verification & Reconcile** | ● | Event: +2s after submit | **P0** | 1 |
| E07 | Protective Order Placement | ● | Event: fill confirmed | **P0** | 1 |

## T — IN-TRADE (10 jobs)

| ID | Job | Lane | Schedule | Crit | Phase |
|---|---|---|---|---|---|
| T01 | Position & P&L Monitor | ● | Every 1s while open | **P0** | 1 |
| T02 | Greeks Drift Monitor | A | Every 30s | P2 | 4 |
| T03 | **Stop Loss Trailing Engine** | ● | Every 1s / bar close | **P0** | 2 |
| T04 | Partial Exit / Scale-Out | ● | Every 1s | P1 | 3 |
| T05 | Breakeven Shift Engine | ● | Every 1s | P1 | 2 |
| T06 | Time Stop Enforcer | ● | Every 10s | P1 | 2 |
| T07 | Adjustment Trigger | A | Every 60s | P3 | 5 |
| T08 | Spread & Liquidity Degradation Monitor | ● | Every 5s | P1 | 3 |
| T09 | Event Proximity Guard | ● | Every 60s | P1 | 3 |
| T10 | Correlation & Exposure Aggregator | ● | Every 30s | P2 | 4 |

## X — EXIT (3 jobs)

| ID | Job | Lane | Trigger | Crit | Phase |
|---|---|---|---|---|---|
| X01 | Exit Execution | ● | Event: exit signal | **P0** | 1 |
| X02 | **Square-off Enforcer** | ● | 15:15 (A) / 23:15 (B2) | **P0** | 1 |
| X03 | Exit Fill Verification | ● | Event: +2s | **P0** | 1 |

## M — POST-MARKET (8 jobs)

| ID | Job | Lane | Schedule | Crit | Phase |
|---|---|---|---|---|---|
| M01 | Broker Reconciliation | ● | 15:45 / 23:45 | **P0** | 1 |
| M02 | Trade Journal Writer | ● | 15:50 | P1 | 2 |
| M03 | P&L & Cost Attribution | ● | 15:55 | P1 | 2 |
| M04 | Slippage & Execution Quality | ● | 16:00 | P2 | 3 |
| M05 | Strategy Metrics Update | ● | 16:05 | P1 | 3 |
| M06 | Regime Log Writer | ● | 16:10 | P2 | 3 |
| M07 | Post-Market Brief | ● | 16:15 | P2 | 3 |
| M08 | Data Archival & Backup | ● | 16:30 | P1 | 2 |

## R — PERIODIC (6 jobs)

| ID | Job | Lane | Schedule | Crit | Phase |
|---|---|---|---|---|---|
| R01 | Weekly Walk-Forward Revalidation | ● | Sat 10:00 | P2 | 5 |
| R02 | **Strategy Decay Monitor** | ● | Sat 10:30 | P1 | 4 |
| R03 | Parameter Drift Detection | ● | Sat 11:00 | P2 | 5 |
| R04 | Risk Budget Rebalance | ● | Sun 10:00 | P2 | 4 |
| R05 | Monthly Performance Review | ● | 1st, 10:00 | P2 | 4 |
| R06 | **Config vs Exchange Audit** | ● | Sat 09:00 | **P0** | 2 |

## K — CROSS-CUTTING (5 jobs)

| ID | Job | Lane | Schedule | Crit | Phase |
|---|---|---|---|---|---|
| K01 | **Kill Switch Controller** | ● | Always-on listener | **P0** | 1 |
| K02 | Alert Router | ● | Always-on | **P0** | 1 |
| K03 | Heartbeat & Watchdog | ● | Every 30s | **P0** | 1 |
| K04 | Audit Log Writer | ● | Event-driven | **P0** | 1 |
| K05 | Config Validator | ● | On change + 08:00 | P1 | 1 |

---

## Daily timeline — LANE A (options, Nifty Tuesday expiry)

```
08:00  P01 ──── auth refresh, health check          [BLOCKS EVERYTHING IF FAIL]
08:05  P02 ──── is today a trading day?
08:10  P03 ──── economic events today?
08:30  P04 ──── GIFT Nifty, global cues, overnight gap estimate
08:45  P05 ──── VIX regime classification
08:50  P06 ──── resolve instrument, expiry, cycle stage S1-S5, lot size
08:55  P07 ──── capital + margin check
09:00  P08 ──── ARM strategies eligible for today's regime+stage
09:05  P09 ──── build strike shortlist from chain
09:10  P10 ──── pre-market brief → Telegram
─────────────────────────────────────────────── MARKET OPEN 09:15
09:15  O01 ──── opening range capture begins
09:16  O03 ──── gap classification + veto
09:45  O02 ──── regime confirmation; OR finalised
09:45+ E01 ──── signal generation active
       E02-E07  entry pipeline on each signal
       T01-T10  monitors run continuously while any position open
15:15  X02 ──── SQUARE-OFF ENFORCER — hard flatten
─────────────────────────────────────────────── MARKET CLOSE 15:30
15:45  M01 ──── broker reconciliation      [ALERTS ON ANY MISMATCH]
15:50  M02 ──── journal
15:55  M03 ──── P&L + cost attribution
16:00  M04 ──── slippage report
16:05  M05 ──── strategy metrics update
16:10  M06 ──── regime log
16:15  M07 ──── post-market brief → Telegram
16:30  M08 ──── archive + backup
```

## Daily timeline — LANE B (gold)

Lane B runs on **session windows, not a single daily cycle**. See `11-INSTRUMENT-LANES.md` §B for the full mapping. Summary in IST:

```
B1 (XAUUSD/MT5, 24/5)          B2 (MCX Gold, 09:00–23:30 IST)
─────────────────────────────  ──────────────────────────────
05:30-14:30  Asian   ★☆☆☆☆     09:00  MCX opens (thin, Asian-hours gold)
13:30-22:30  London  ★★★★☆     13:30  London opens ── volatility arrives
18:30-22:30  OVERLAP ★★★★★     18:30  OVERLAP ── prime window
22:30-03:30  NY      ★★★☆☆     19:00  US data releases hit
03:30-05:30  Dead    ☆☆☆☆☆     23:15  X02 square-off
                                23:30  MCX closes
```

**Key insight:** the MCX evening session (18:30–23:30 IST) covers the London/NY overlap — the single best gold scalping window. Lane B2 gets ~85% of the opportunity of 24/5 XAUUSD, legally and domestically, in a 5-hour evening window that does not conflict with Lane A's morning session.

---

## Job dependency graph

```
P01 ──┬─▶ P02 ─▶ P03 ─▶ P04 ─▶ P05 ─┬─▶ P08 ─▶ P09 ─▶ P10
      │                              │
      └─▶ P06 ─▶ P07 ────────────────┘
                                      │
                          O01/O03 ────┴──▶ O02 ──▶ E01
                                                     │
                          E01 ─▶ E02 ─▶ E03 ─▶ E04 ─▶ E05 ─▶ E06 ─▶ E07
                                 │                            │
                              (RISK ENGINE gate)         (on fail: E05 rollback)
                                                              │
                                                              ▼
                                            T01 ─┬─ T03 ─ T04 ─ T05 ─ T06
                                                 ├─ T02 (A) ─ T07 (A)
                                                 └─ T08 ─ T09 ─ T10
                                                              │
                                            X01/X02 ─▶ X03 ───┘
                                                              │
                          M01 ─▶ M02 ─▶ M03 ─▶ M04 ─▶ M05 ─▶ M06 ─▶ M07 ─▶ M08

K01-K05 run independently and can interrupt ANY of the above.
```

**Hard rule:** if `P01`, `P06` or `P07` fails, nothing downstream runs. No auth, no instrument resolution, or no capital check means no trading — full stop, alert human.

---

## Criticality summary

| Criticality | Count | Meaning |
|---|---|---|
| **P0** | 18 | Capital-protecting. System does not trade without these. Build first. |
| P1 | 16 | Core function. Build in Phases 2–3. |
| P2 | 10 | Valuable. Phases 3–4. |
| P3 | 2 | Nice-to-have. Phase 5. |

**Phase 1 delivers all 18 P0 jobs and nothing else.** That is a system that can enter, protect, exit and reconcile a single manual-signal trade safely. Everything after is expansion. See `13-IMPLEMENTATION-ROADMAP.md`.
