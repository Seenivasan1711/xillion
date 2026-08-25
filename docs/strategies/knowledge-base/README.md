# Options Scalping Strategy Knowledge Base

Source: `optionsscalpingrag.zip`, supplied by Rakesh 2026-08-25. Stored here
verbatim (file names and content unchanged from the zip) for git history and
future RAG ingestion into prosper-engine's Chroma store (same pattern as
`scripts/ingest_xillion.py` already uses for `docs/strategies/*.md`).

## What this is

A structured, source-cited reference on Indian index-options intraday and
short-cycle strategies — NSE Nifty weekly, NSE monthly (Bank Nifty/FinNifty/
MidCpNifty), and BSE Sensex weekly. Built to be used as RAG context by an AI
assistant helping analyse a live session, **not** a set of trade signals and
**not** a claim that any strategy here is profitable. Every numeric claim
carries a confidence tier (T1 real backtest → T5 no data) — see `00-INDEX-AND-USAGE.md`.

**Always load `00-INDEX-AND-USAGE.md` first** — it defines the confidence-tier
system and the behavioural rules any AI using this knowledge base must follow
(never invent a number, always state max loss first, flag regime mismatch,
etc.).

## The headline recommendation

- **Backtest first:** Rank 1 in `07-RANKED-LOW-RISK-HIGH-WIN.md` — the
  Nifty/Sensex weekly Bull Put / Bear Call **credit spread** (2-leg, defined
  risk). Full mechanical spec, including the arm matrix to test and the
  pass/fail criteria to apply before ever going live, is in
  `10-FIRST-STRATEGY-SPEC.md`.
- **Live trading candidate once backtested:** the long butterfly
  (`06-BAG-D-DEBIT-AND-EXOTIC.md` §D1) — max loss ~₹1,600/lot, the lowest
  absolute rupee risk in the knowledge base.
- **The single most important page:** `07-RANKED-LOW-RISK-HIGH-WIN.md`'s
  "arithmetic that governs everything" section — the standard "sell 20-delta,
  take 50%, stop at 200%" recipe does **not** clear its own break-even win
  rate on the delta math alone. Any edge has to come from the variance risk
  premium, which the cited research found **inverted** in early 2026.

## File map

| File | Contains |
|---|---|
| `00-INDEX-AND-USAGE.md` | Confidence-tier system + AI behavioural rules — load first |
| `01-MARKET-STRUCTURE.md` | Expiry calendar, lot sizes (Nifty 65, Sensex 20), costs, SEBI/margin rules |
| `02-VARIABLES-GLOSSARY.md` | Every decision variable + thresholds (VIX, IVR, VRP, Greeks, OI, PCR, ATM straddle) |
| `03-BAG-A-SELLING-DEFINED-RISK.md` | Iron condor, credit spread, iron fly, 0DTE spread, covered call |
| `04-BAG-B-SELLING-UNDEFINED-RISK.md` | Naked/unhedged credit strategies — reference + warning only |
| `05-BAG-C-BUYING-DIRECTIONAL.md` | ORB, VWAP pullback, momentum/breakout option buying |
| `06-BAG-D-DEBIT-AND-EXOTIC.md` | Butterfly, BWB, calendar, ratio spreads |
| `07-RANKED-LOW-RISK-HIGH-WIN.md` | **The master ranking** + the break-even-win-rate arithmetic |
| `08-DAILY-DECISION-ENGINE.md` | Deterministic IF/THEN gates: market state → strategy shortlist |
| `09-BACKTEST-PROTOCOL.md` | The 10+1 rules for honestly validating a strategy |
| `10-FIRST-STRATEGY-SPEC.md` | Full mechanical spec for the recommended starting strategy |
| `11-SOURCES-AND-CONFIDENCE.md` | Source ledger, confidence tiers, known-stale-claims warnings |

## Cross-reference

The execution harness this knowledge base plugs into is specified separately
in [`docs/architecture/automation-platform-spec/`](../../architecture/automation-platform-spec/).
That spec's own words: *"strategies are hypotheses with a short shelf life,
the harness is infrastructure."*
