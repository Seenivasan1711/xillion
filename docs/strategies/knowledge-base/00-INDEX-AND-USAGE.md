---
doc_id: 00-INDEX
title: Index and Usage Contract
topic: how-to-use-this-knowledge-base
compiled: 2026-08-24
owner: Rakesh
use_when: ALWAYS load this file first. It defines how every other file must be interpreted.
---

# 00 — INDEX AND USAGE CONTRACT

## What this knowledge base is

A structured reference on **Indian index-options intraday and short-cycle strategies**, built to be used as RAG context by an AI assistant that will help analyse a live/ongoing market session and recommend which strategy (if any) fits current conditions.

It covers NSE Nifty weekly options, NSE monthly index options (Bank Nifty / FinNifty / MidCpNifty), and BSE Sensex weekly options.

## What this knowledge base is NOT

- It is **not** a set of trade signals.
- It is **not** a claim that any strategy listed here is profitable.
- It contains **no live market data**. Every price, level, OI, IV and VIX value must come from the user's charts or a live data feed at query time.

## File map

| File | Contains | Load when |
|---|---|---|
| `00-INDEX-AND-USAGE.md` | This contract | Always |
| `01-MARKET-STRUCTURE.md` | Expiry calendar, lot sizes, costs, SEBI rules, margin | Always (grounds every strike/size decision) |
| `02-VARIABLES-GLOSSARY.md` | Every decision variable + thresholds + how to read it | When classifying current market state |
| `03-BAG-A-SELLING-DEFINED-RISK.md` | Defined-risk credit strategies by expiry-cycle stage | When market state favours premium selling |
| `04-BAG-B-SELLING-UNDEFINED-RISK.md` | Naked/unhedged credit strategies | Reference + warning only |
| `05-BAG-C-BUYING-DIRECTIONAL.md` | Option buying, scalping, momentum, breakout | When a directional edge is present |
| `06-BAG-D-DEBIT-AND-EXOTIC.md` | Butterflies, calendars, ratio spreads, BWB, jade lizard | Niche / specific-view setups |
| `07-RANKED-LOW-RISK-HIGH-WIN.md` | **The master filtered ranking** | When user asks "what should I trade / what's safest" |
| `08-DAILY-DECISION-ENGINE.md` | Deterministic IF/THEN rules mapping market state → strategy | Every live-market query |
| `09-BACKTEST-PROTOCOL.md` | How to validate a strategy honestly | When user asks about backtesting |
| `10-FIRST-STRATEGY-SPEC.md` | Full spec of the single recommended starting strategy | When user asks "what do I start with" |
| `11-SOURCES-AND-CONFIDENCE.md` | Source ledger, confidence tiers, known-stale warnings | When user asks "how do you know this" |

## Confidence tier system — MANDATORY

Every numeric claim in these files carries a tier. **You must surface the tier whenever you quote a number.**

| Tier | Code | Meaning |
|---|---|---|
| **T1** | `[T1-BACKTEST]` | A real backtest with stated sample size, period and metrics |
| **T2** | `[T2-RESEARCH]` | Peer-reviewed / preprint academic study, methodology disclosed |
| **T3** | `[T3-VENDOR]` | Broker or education site states a number with no disclosed methodology |
| **T4** | `[T4-STRUCTURAL]` | Mathematically true by construction (e.g. "max loss = width − credit") |
| **T5** | `[T5-UNQUANTIFIED]` | Rules exist, no performance data found anywhere |

**Rule:** T3 numbers are marketing until proven otherwise. Never present a T3 win rate as an expectation. T4 facts are the most reliable content in this entire knowledge base because they are arithmetic, not claims.

## Behavioural rules for the AI using this knowledge base

1. **Never invent a number.** If a win rate is not in these files, say it is not known. Do not interpolate, average, or estimate one.
2. **Never give a trade recommendation without live data.** If the user has not supplied current spot, IV/VIX, OI and chart structure, ask for it or state which inputs are missing.
3. **Always state max loss in rupees before discussing profit.** For any structure you describe, compute worst case first using the lot sizes in `01`.
4. **Distinguish win rate from expectancy, every single time.** A high win rate with a large average loss is a losing strategy. See `07` §Expectancy Math.
5. **Flag regime mismatch.** If current India VIX / IV rank is outside a strategy's stated favourable band, say so before anything else.
6. **Prefer defined risk.** When two candidate strategies have similar expectancy, recommend the one with a capped max loss.
7. **Never encourage size increases after a winning streak**, revenge trading after losses, or removing a stop to "give the trade room". These are the documented failure modes.
8. **Cite the file and tier.** e.g. "per `03-BAG-A` §Iron Condor `[T3-VENDOR]`".
9. **Stale-source vigilance.** Indian F&O rules changed materially in Nov 2024, Sep 2025, Jan 2026 and Apr 2026. If the user quotes a strategy referencing Thursday Nifty expiry or weekly Bank Nifty, it predates the current regime — flag it. See `11` §Known Stale Claims.
10. **This is analysis support, not financial advice.** The user makes every decision. Do not use language that implies certainty of profit.

## The user's stated objective

> "Very low risk and high chance of getting profit. I don't need huge amounts — I need very good winning probability."

**How to serve this honestly:** In options, win rate and risk are not independent. The structures with the highest raw win rates (naked short straddles/strangles) are the ones with unbounded loss. The genuine answer to "low risk + high win probability" is **defined-risk premium selling with mechanical management** — see `07` for the full ranked answer and the arithmetic that explains why.

Do not resolve this tension by simply handing over the highest win-rate number in the files. That number belongs to the most dangerous structure in them.
