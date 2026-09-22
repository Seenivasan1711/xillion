# Strategy: Gold XAUUSD Sweep-Reversal (session sweep)

> One file per strategy. Written at Stage 1, updated at every pipeline stage.
> **These files are ingested into the RAG layer (CP8)** — the assistant answers
> "why did this strategy fail last October?" from here, so write for a reader
> with no memory of the conversation.

**Asset class:** gold (Lane B1, XAUUSD)
**Broker:** Funding Pips (MT5) — planned for eventual execution. **v1 runs in
alert-only mode, decoupled from the MT5 broker/bridge entirely** — no Wine/MT5
terminal setup is required to get alerts flowing (see §7). Execution through
`brokers/mt5_funding_pips.py` is a later stage, once the edge is validated.
**Status:** 🔴 Stage 2 backtest run for real 2026-09-22, real 6-month result —
**net loss, not a pass**. See §3. Alert-only instance (Stage "S3-lite":
notification only, no execution, no real capital at risk) has been running
live since 2026-09-22 regardless, since alerting was always decoupled from
whether this specific parameter set is fundable — see §7. **Do not size up
capital or move to real paper/live trading on these exact parameters without
addressing §3's R:R finding first.**
**Created:** 2026-09-21 · **Last updated:** 2026-09-22

---

## 1. The rules (plain language)

**Instrument:** XAUUSD only. **Trading window:** 12:30–18:30 IST (London
session) only — no trades outside it.

**Daily prep (5 min, once a day):** mark exactly 4 horizontal lines, nothing
else:
- Asian session HIGH (05:30–12:30 IST)
- Asian session LOW
- Previous day HIGH
- Previous day LOW

**Entry trigger** (the only thing watched intraday):
1. Price trades **beyond** one of the 4 lines (a "sweep")
2. An **M5 candle closes back inside** the line
3. Enter at market on that close, **opposite** the sweep direction (i.e. a
   fade of the sweep — sweep above a resistance line + close back under it →
   short; sweep below a support line + close back above it → long)
4. **Stop-loss:** 0.5 pts beyond the wick extreme of the sweep, **minimum
   3.0 pts** from entry (whichever is further)
5. **Target:** entry ± **7.5 pts** (fixed, not ATR-scaled)

**Position sizing (fixed forever — never adjust):**

| | |
|---|---|
| Lot size | 0.08 |
| Risk per trade | −$24 |
| Target per trade | +$60 |
| R:R | 2.5 : 1 |
| Max trades/day | 2 |

Never move the stop once placed. No partial exits. No re-entry on the same
line/session once stopped out. If both daily trades lose, done for the day —
no more signals until the next session.

**What edge is this exploiting?** A liquidity sweep past a well-known level
(Asian range or prior day range) followed by a fast reclaim is read as a stop
hunt / failed breakout — the sweep traps late breakout entries and momentum
reverses back into range. This is a well-documented smart-money/liquidity-grab
pattern on London-session gold; the edge is the *failure* of the breakout, not
the breakout itself. **If win rate lands materially below the ~32% breakeven
in the 4-day test (§4), the level-fade read isn't holding on this instrument/
timeframe and the strategy should be killed, not patched (§4's keep/kill
table) — resist adding a 5th condition.**

**Filters:**
- Session: London window only (12:30–18:30 IST); see §6 for the fuller
  session-quality table (Overlap is rated better than plain London, but this
  card trades London only — Overlap is a possible parameter change to test,
  not adopted yet)
- No entry within 15 minutes of a red-folder USD economic release
- Skip if spread > 0.30 pts

## 2. Why these numbers (prop-firm rule mapping)

Reverse-engineered from the **FundingPips 1 Step Flex $5K** account rules so
none of this has to be reasoned about mid-trade:

| Constraint | Handled by |
|---|---|
| $50 floating loss = permanent Striking System warning | 0.08 lot × 3.0 pt min SL = **$24 heat**, half the threshold |
| 10-min same-direction grouping rule | "Never re-enter" |
| 3% daily loss cap = $150 | 2 trades × $24 = **$48 max** daily heat |
| 12% static drawdown = $600 | 25 straight losses needed to breach |
| 60% single-trade profit concentration rule = $360 cap | a $60 winner is 17% of that cap |

**Yield math** (2 trades/day, ~20 trading days/month):

| Win rate | Per trade (expectancy) | Per month (gross) |
|---|---|---|
| 35% | +$2.90 | $116 |
| 40% | +$7.10 | $284 |
| **45%** | **+$11.30** | **$452 ✅ (target)** |
| 50% | +$15.50 | $620 |

Breakeven ≈ **32%** win rate. Target to clear $400/mo net of FundingPips'
85% profit split: **45%**. That single number is what Stage 2 (backtest) and
the manual 4-day test below exist to find — nothing else about this strategy
should be tuned before that number is known.

## 3. Backtest results (Stage 2) — **run for real 2026-09-22, result: net loss**

| Period | Regime | Trades | Win % | Total P&L | Max DD | Sharpe |
|---|---|---|---|---|---|---|
| 2026-03-23 → 2026-09-21 (6mo, real Twelve Data XAUUSD M5, both sessions combined) | Live market, mixed | 201 | **47.8%** | **-$12,705.76** (-254%) | **$12,764.66 (252%)** | 0.044 |

Full metrics: 96 wins / 105 losses, avg win $38.82, avg loss $129.56,
**profit factor 0.274**, expectancy **-$49.14/trade**. Ran through
`BacktestEngine` end-to-end (not the external reference script) using
`data_providers/twelve_data_history.py` (Stage 1's own historical provider)
+ `strategies/gold_sweep_reversal.py` exactly as coded, `initial_capital`
$5,000 (matching the card's $5K account), `slippage_bps=5`, fixed 0.08 lot.

**🔴 Win rate alone says "keep" per the card's own table (≥45%) — but the
account would have been wiped out (final equity -$7,705.76, deeper than
the $600 static floor a real FundingPips account enforces) inside these
6 months.** The card's yield math (§2) assumed a fixed ~2.5:1 R:R (7.5pt
TP vs. a "typical" 3.0pt SL). That assumption doesn't hold in practice:

| | Card assumed | Actual (this run) |
|---|---|---|
| Avg win | 7.5 pts (fixed TP) | 6.63 pts (slippage) |
| Avg loss | ~3.0 pts (the stated "minimum") | **14.43 pts** (median 11.58, range 7.07–75.53) |
| R:R | 2.5 : 1 | **~0.46 : 1** |

**Why:** the rule is "SL = `sl_buffer_pts` beyond the sweep's wick extreme,
**minimum** `min_sl_pts` (3.0)" — the 3.0pt figure is a floor, not a
typical value, and it almost never binds. On a real, sometimes-violent
sweep, the wick extreme is frequently 10-75 points beyond entry, and the
mechanical rule sizes the stop there every time. The card's own yield
table implicitly assumed the floor would usually be what fires; it doesn't
in this real sample. Per-level breakdown (all four are money-losers this
period, not just one bad line): Asian Low 77 trades/44.2% win/-$3,823.60,
Asian High 80/45.0%/-$4,693.56, PD High 17/64.7%/-$485.44, PD Low
27/55.6%/-$874.45 — dropping the worst single line (§4's "one allowed
simplification") would not have flipped this to profitable on its own.

**Per the card's own keep/kill framework (§4), this needs a real decision,
not an automatic "run it live" just because win rate cleared 45%** — the
framework's threshold assumed the R:R held, and it doesn't.

### Parameter sweep, 2026-09-22 — the SL floor/cap isn't the fix either

Two grid searches against the same 6-month sample, via `grid_search()`
(`xillion/engine/optimization.py`):

1. **`tp_pts` × `min_sl_pts`** (6 × 5 = 30 combos, `min_sl_pts` from 3-15pt):
   every single combination came back net-negative. The original params
   (7.5 / 3.0) were actually the **least bad** of all 30 — every wider
   `min_sl_pts` made things worse, not better.
2. **`tp_pts` × `max_sl_pts`** (3 × 9 = 27 combos, a new **hard cap**
   regardless of the wick extreme — see `max_sl_pts` in `params_schema`,
   added specifically to test this): still every combination net-negative.
   Best found: -$12,672.71 (`tp_pts=7.5, max_sl_pts=10.0`) — barely better
   than the -$12,705.76 baseline. Profit factor never rose above ~0.30
   regardless of how tightly the stop was capped: a tighter cap trades
   fewer/smaller losses for a lower win rate (more stop-outs), and those
   roughly cancel out.

**Conclusion: within this parameter space, no TP/SL combination makes this
edge profitable on this real 6-month window.** That points at the "fade
the sweep" signal itself, not just its risk sizing, being the issue for
this specific period — capping or widening the stop doesn't rescue it.
Options, undecided as of this writing: (a) accept this parameter *family*
doesn't have an edge here and treat it as killed — the card's own §4 rule
("<38%: not your edge... do NOT patch with a 5th rule") arguably applies
in spirit even though win rate itself was above 38%, since R:R is what's
actually broken; (b) test whether a materially different regime (a
different symbol, a longer/different historical window, or a genuinely
different TP model — e.g. targeting the sweep's own retracement distance
rather than a fixed 7.5pt) changes the picture, which is new analysis, not
a parameter tweak; (c) drop to Asian-only or PD-only lines (§4's "one
allowed simplification") and re-test — per-level stats above show none of
the four lines were profitable individually either, so this is unlikely to
flip the sign, but hasn't been directly re-tested with level-dropping
combined with the sweeps above. **Not decided in this session — a
strategy-viability call, not engineering.**

- **Data source + timeframe:** `data_providers/twelve_data_history.py`
  (Stage 1, this repo's own `HistoricalDataProvider`), real M5 XAUUSD,
  fetched live from Twelve Data's free tier. The external reference script
  below was NOT used for this run (would need a real MT5 terminal/Windows
  box, which doesn't exist in this environment) — kept here for the user's
  own manual validation (§4) instead.
- **Parameter sensitivity:** not yet swept (no `/optimize` run against these
  params yet — a natural next step given §3's finding, e.g. sweeping
  `tp_pts`/`min_sl_pts`/`sl_buffer_pts` to see whether a real profitable
  combination exists at all before concluding the setup itself is dead).
- **Manual spot-check:** not done — §4's TradingView-replay protocol is
  still the user's own, external, not-yet-run process.
- **Three real bugs found and fixed getting this backtest to run at all**
  (not specific to this strategy's numbers, all in shared engine code):
  `_BacktestContext` had no `notify()` override (crashed on the first
  entry); `BacktestEngine` never synthesized an `on_tick` for a plain
  (non-options) strategy's own primary symbol, so SL/TP monitoring never
  ran and a position never closed; `_roll_day` fired on each day's very
  first bar (always ~00:00 UTC, inside the Asian session), so that day's
  own Asian-session bars weren't in history yet — Asian High/Low came back
  missing on literally every day until fixed. Also found and fixed: a
  sparse/empty `params` dict crashed on the first `ctx.params` access
  (fixed for every backtest/instance endpoint, not just this strategy), and
  `compute_metrics`'s CAGR calculation crashed outright on an account this
  deeply negative (fixed to floor at -100%, not specific to Gold either).

### Reference backtest tool (external, not part of the live pipeline)

`scripts/gold_sweep_backtest.py` is a standalone research script, not wired
into xillion's `BacktestEngine` or strategy-plugin system — it's the tool
the strategy card ships with, kept here verbatim so it's version-controlled
and doesn't need to be re-pasted into a future session.

```bash
pip install MetaTrader5 pandas numpy   # MetaTrader5: Windows only

python scripts/gold_sweep_backtest.py                    # XAUUSD, 6 months, from MT5
python scripts/gold_sweep_backtest.py data.csv            # use a CSV instead (Mac/Linux)
python scripts/gold_sweep_backtest.py --symbol GOLD --months 12
python scripts/gold_sweep_backtest.py --tp 10 --sl 4 --lot 0.05
python scripts/gold_sweep_backtest.py --offset 2          # winter (broker on UTC+2)
python scripts/gold_sweep_backtest.py --db ""              # skip SQLite, CSV only
```

**Before the first run:**
1. **Symbol name** — brokers rename gold (`XAUUSD`, `XAUUSD.r`, `XAUUSDm`,
   `GOLD`). If wrong, the script prints every gold symbol available on the
   connected broker.
2. **Server offset** — most brokers run EET (UTC+3 summer / UTC+2 winter).
   The script self-checks by finding gold's quietest trading hour (should be
   ~21:00–23:00 UTC) and warns with a suggested `--offset` if it looks wrong.
   Don't ignore that warning — a wrong offset shifts every session boundary
   and invalidates the whole test.
3. *"Only N M1 bars — not enough"* → open an M1 XAUUSD chart in the MT5
   terminal and scroll back several months; MT5 only downloads history that's
   actually been viewed.

**Output:** `sweep_trades.csv` (flat) + `sweep.db` (SQLite, append-only —
every run accumulates so runs stay comparable across parameter changes).
- `runs` table: one row per backtest — every parameter used plus headline
  stats (`trades`, `win_rate`, `expectancy`, `per_month`, `max_dd`,
  `worst_streak`, `strikes`, `breached`, …).
- `trades` table: one row per trade, linked by `run_id` — `session`, `date`,
  `line` (which of the 4 levels), `direction`, `entry`/`sl` details,
  `exit`/`outcome`, `net_pts`, `pnl`, `equity`, `mfe_pts` (best excursion
  before the stop — answers "should the TP be wider"), `heat_pts`/`heat_usd`
  (worst adverse excursion; `heat_usd >= 50` = a Striking System warning in
  backtest).

**Reading the output:** check expectancy **and** max DD together (a better
per-trade number with an unsurvivable drawdown is useless on a $600 budget);
check month-by-month consistency (one huge month carrying five flat ones is
not an income system); check the TP-sweep **Strikes** column (4+ closes the
account); check the worst losing streak is actually sittable; check per-level
performance — **if one of the 4 lines loses consistently, dropping it is the
one allowed simplification** (§4's keep/kill table).

**Two caveats baked into the numbers:** (1) when a stop and a target are both
touched inside the same M1 bar, the script assumes the **stop hit first** —
conservative, so live should be slightly better than the backtest. (2) spread
is modelled flat at 0.20 pts; real spread widens at the London open and
around news — exactly when this strategy trades — so treat the backtest
output as the **optimistic case**. If it only clears $400/month by a hair, it
doesn't actually clear it.

## 4. The 4-day manual validation test (Stage 2, human-run — not automated)

TradingView bar replay, M5, XAUUSD, hide the right side, random start date in
the last 6 months. **Skip forward through Asian and post-NY hours — only
replay 12:30–18:30 IST.**

| Day | Job | Trades |
|---|---|---|
| 1 | Learn to spot it. Don't count results | ~20 |
| 2 | Run it clean, log everything | ~30 |
| 3 | Continue | ~30 |
| 4 | Finish sample, compute stats | ~30 |

Need **100+ trades** for the win rate to mean anything — below 50 is noise.

**Making replay actually pressure-test it:**
1. Run a cumulative equity column starting at $5,000. If it touches $4,400,
   the test is over — same as the real account would be.
2. After the replay sample, run **10 trading days on live demo in real time**
   during the actual London window. Real spread, real waiting, real boredom
   — that's where you find out whether the setup is actually sittable.

**Keep/kill, after 100 trades:**

| Result | Action |
|---|---|
| **≥45%** | Run on 2 Step Pro or live demo 2 weeks, then funded |
| **38–44%** | Edge is real but thin. Change **ONE** variable (likely: drop prev-day lines, keep Asian only), re-test 100 more |
| **<38%** | Not the edge at these parameters. Do **not** patch with a 5th rule |

> Resist adding conditions when a test disappoints. Every added rule makes
> the system unfollowable and shrinks the sample size that can ever be
> collected on it.

## 5. Paper results (Stage 3) — not started

Cannot start until Stage 2 (§3/§4) produces a keep decision.

## 6. Live results (Stage 4) — not started

### Session reference (for context, not yet acted on)

| Window (IST) | UTC | Quality |
|---|---|---|
| 18:30–22:30 | 13:00–17:00 | **Best** — London/NY overlap |
| 12:30–18:30 | 07:00–13:00 | Good — London (the window this card trades) |
| 04:00–11:00 | 22:30–05:30 | Worst — Asian chop, do not trade |

## 7. Failure log

| Date | What happened | Failure mode | Change made |
|---|---|---|---|
| 2026-09-22 | First real 6-month backtest: 47.8% win rate (above the card's own 45% threshold) but net loss of $12,705.76 on a $5,000 account -- realized SL averaged 14.43 pts vs. the card's assumed ~3.0 pt typical, since the "minimum 3.0pt" floor rarely binds against a real wick extreme | `regime_change` (the mechanical rule's real risk profile doesn't match the card's own yield-math assumption) | None yet -- flagged for a strategy-viability decision (see §3), not patched |

Failure modes: `stopped_out` · `target_missed` · `late_entry` · `slippage` ·
`no_fill` · `gap` · `regime_change` · `data_gap` · `system_error`

**Note on the live-alert data path vs. the backtest script's data path**
(recorded here now since it's a real, deliberate divergence — not an
oversight): the reference backtest script (§3) pulls M1 bars straight from a
running MT5 terminal, which on Mac only works through Wine — that's a real
local-machine dependency. **The live alert engine (Stage 3+ build, tracked in
`docs/status/task-tracker.md`) intentionally does not use that path for v1.**
It runs in alert-only mode (signals + Telegram notification, no order
placement), so it doesn't need the MT5 bridge or Wine at all — a free
intraday-capable price API supplies the M5 candles instead. This means the
live alert's price feed and the backtest's price feed are **two different
data sources** until Lane B1's MT5 broker/bridge is actually verified end to
end (still open per `docs/status/manual-tasks.md`) — expect some feed
discrepancy vs. the exact MT5 print (spread/latency), which matters for a
scalping strategy with a 3.0 pt minimum stop and should be watched for once
alerts are live, not assumed away.

## 8. Version history

| Version | Date | Change | Why |
|---|---|---|---|
| v1 | 2026-09-21 | Initial rules encoded from the user's card, verbatim | Stage 1 |
| v1 | 2026-09-22 | Real Stage 2 backtest run (no rule changes) -- 6mo, 201 trades, net loss found | Stage 2 |
