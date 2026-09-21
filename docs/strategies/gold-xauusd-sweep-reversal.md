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
**Status:** Stage 1 build (rules encoded, this doc) — Stage 2 backtest **not
yet run in this repo**. The user's own MT5/TradingView-replay validation
(§4) is an external process and hasn't been done yet either.
**Created:** 2026-09-21 · **Last updated:** 2026-09-21

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

## 3. Backtest results (Stage 2) — **not yet run**

| Period | Regime | Trades | Win % | Total P&L | Max DD | Sharpe |
|---|---|---|---|---|---|---|
| *(none yet)* | | | | | | |

- **Data source + timeframe:** the reference script
  [scripts/gold_sweep_backtest.py](../../scripts/gold_sweep_backtest.py) pulls
  M1 bars directly from a running MT5 terminal (Windows-only `MetaTrader5`
  package; Mac/Linux must export a CSV from MT5 instead) and resamples to M5
  for the entry logic — see §7 for why this repo's live alert engine will
  **not** use this same data path.
- **Parameter sensitivity / manual spot-check:** not done yet — blocked on
  either running the script against real MT5 history or completing §4's
  manual replay test first.

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
| | | | |

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
