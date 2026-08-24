# Strategy: <NAME>

> One file per strategy. Written at Stage 1, updated at every pipeline stage.
> **These files are ingested into the RAG layer (CP8)** — the assistant answers
> "why did this strategy fail last October?" from here, so write for a reader
> with no memory of the conversation.

**Asset class:** options | gold | forex | stock options | stocks | crypto
**Broker:** Zerodha | Funding Pips (MT5) | …
**Status:** Stage 1 build | Stage 2 backtest | Stage 3 paper | Stage 4 live | Stage 5 automated
**Created:** YYYY-MM-DD · **Last updated:** YYYY-MM-DD

---

## 1. The rules (plain language)

State it so someone with no context could trade it manually.

- **Universe:** which instruments, which expiry/strike selection
- **Entry:** exact condition
- **Exit:** exact condition
- **Target:** how computed
- **Stop-loss:** how computed
- **Position sizing:** lots/qty and how derived
- **Filters:** time-of-day, volatility regime, trend, news blackouts
- **What edge is this exploiting?** — if you can't answer this, expect it to
  stop working without warning

## 2. Backtest results (Stage 2)

| Period | Regime | Trades | Win % | Total P&L | Max DD | Sharpe |
|---|---|---|---|---|---|---|
| | | | | | | |

- **Parameter sensitivity:** does it survive ±10% on each parameter?
- **Manual spot-check:** N trades verified by hand — matched / didn't match
- **Data source + timeframe used:**

## 3. Paper results (Stage 3)

**Window:** YYYY-MM-DD → YYYY-MM-DD (must be ≥2 weeks of market days)

- Signals fired vs. expected
- **Divergences from backtest, and why** ← the most valuable section here
- Timing issues, missed/duplicate signals
- Observed slippage vs. assumed

## 4. Live results (Stage 4)

- First live date, size traded
- **Real vs. paper:** fills, fees, slippage
- Fee/slippage corrections fed back into the backtest config

## 5. Failure log

The point of the whole system. Every loss worth learning from:

| Date | What happened | Failure mode | Change made |
|---|---|---|---|
| | | | |

Failure modes: `stopped_out` · `target_missed` · `late_entry` · `slippage` ·
`no_fill` · `gap` · `regime_change` · `data_gap` · `system_error`

## 6. Version history

| Version | Date | Change | Why |
|---|---|---|---|
| v1 | | initial | |
