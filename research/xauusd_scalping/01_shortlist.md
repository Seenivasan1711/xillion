# XAUUSD Scalping — Strategy Landscape Sweep (P1)

**Method note:** real web research was performed (WebSearch + WebFetch), not
simulated. Every statistic below is either quoted from a source with a link,
or explicitly marked "no verifiable number." Nothing was estimated and
presented as sourced.

**Important context this search surfaced that the deliverable spec didn't
ask for but changes the ranking:** this repo's own `gold_sweep_reversal.py`
(a liquidity-sweep/stop-hunt reversal rule — trade the reclaim after price
wicks through a level) was rigorously backtested here already: 6 months of
real XAUUSD M5 data, 201 trades, 47.8% win rate, but net -$12,705.76 on a
$5,000 account because realized R:R (~0.46:1) was far worse than assumed
(2.5:1), and 160+ follow-up parameter-sweep combinations (session window,
level richness, finer SL/TP) all stayed net-negative. That is a **T1-tier
result** (our own code, our own data, fully reproducible) and it directly
contradicts the liquidity-sweep mechanism's marketing-tier claims found
below (60-80%+ win rates, T3, unsourced). **Liquidity-sweep/stop-hunt is
excluded from the top 5 on this basis — not because the mechanism is
theoretically unsound, but because it has already failed a more rigorous
test than any external source here can show for it.**

## Candidates evaluated (16 total, before narrowing to 5)

| # | Candidate | Mechanism (one line) | Evidence tier | Edge plausibility | Codeability | Signal freq | Spread/slippage robustness | Independence | Score* |
|---|---|---|---|---|---|---|---|---|---|
| 1 | VWAP σ-band mean reversion | Fade price >=2σ from session VWAP, target reversion | T2 | 4 | 5 | 4 | 3 | high | **4.05** |
| 2 | EMA-trend pullback + breakout (state machine) | Trade WITH an EMA-confirmed trend after a 1-3 bar countertrend shakeout | T1/T2 | 4 | 4 | 3 | 4 | high | **3.85** |
| 3 | Session opening-range breakout (ORB) | Trade the break of the first N-minute range at session open | T2 | 3 | 5 | 4 | 3 | high | **3.65** |
| 4 | ATR/Keltner volatility-squeeze breakout | Trade the expansion that follows a measured compression (low ATR/BB-width) regime | T3 (mechanism has real academic support: volatility clustering) | 3 | 4 | 3 | 3 | high | **3.20** |
| 5 | Rolling-high/low breakout + ADX/EMA trend filter | Trade a break of the rolling N-hour high/low, filtered by trend strength (ADX) and direction (EMA slope) | T2 (open-source, stated param-scan tooling, exact win-rate/PF not independently re-verified by me) | 3 | 4 | 3 | 3 | medium (overlaps somewhat with #3) | **3.10** |
| 6 | Regime-filtered VWAP microstructure + EMA dynamic exit (Bhatti, SSRN) | VWAP-microstructure entry, EMA-based dynamic exit, explicit regime filter | T1 claimed (peer-reviewed-style paper), **but full text was 403/paywalled — only abstract-level stats verifiable** | 4 | 2 (methodology not fully accessible) | unknown | unknown | overlaps with #1 | 2.85 |
| 7 | Liquidity sweep / stop-hunt reversal (ICT/SMC) | Fade a wick through a prior level once price closes back inside | T3 (unsourced 60-80%+ win-rate claims) **+ our own T1 result: net -$12.7k over 6mo, 160+ combos all negative** | 2 (contradicted by our own data) | 4 | 3 | 3 | — | **2.55 — EXCLUDED, see note above** |
| 8 | RSI(M5) overbought/oversold mean reversion | Fade RSI>70 / <30 | T3 (blog-only, "no study confirms this pattern at 5-min timescale" per one source) | 2 | 5 | 5 | 2 | medium (overlaps with #1) | 2.85 |
| 9 | Bollinger Band mean-reversion/breakout (dual-use) | Fade band touches OR trade band breaks — sources disagree on direction | T3 (contradictory claims: "60-70% win rate" one source, "doesn't work well anymore" another) | 2 | 4 | 4 | 2 | low (mechanically ambiguous) | 2.60 |
| 10 | Asian-range fade ("Goldmine Strategy") | Fade the Asian session's own high/low before London open | T3 ("80% win rate" claimed with zero methodology — a marketing red flag per the spec's own T3 definition) | 2 | 4 | 3 | 2 | low (mechanism overlaps with excluded #7) | 2.15 |
| 11 | Pin-bar / candlestick reversal at S/R | Enter on a long-wick reversal candle at a marked level | T3 (all sources are blog/guide content, no stated sample size; best claim is "daily charts," not intraday) | 2 | 3 | 3 | 2 | low | 2.35 |
| 12 | Chinese gold/silver futures "night effect" momentum-after-reversal | Academic finding of intraday momentum following a reversal, tied to specific session/liquidity structure of Chinese futures exchanges | T1 (peer-reviewed) but **low transferability** — market microstructure (trading hours, settlement, participant mix) doesn't map onto XAUUSD spot/CFD | 2 | 2 | unknown | unknown | — | 2.20 |
| 13 | Time-series momentum via realized semivariance | Academic: signed realized semivariance predicts TS-momentum reversals | T1 (peer-reviewed) but designed for **daily/multi-day** momentum, not a 2-8/day scalping frequency; needs care to adapt | 3 | 2 (needs adaptation) | low as-is | unknown | — | 2.30 |
| 14 | 0DTE/short-term ORB variants (equity index options literature) | Same ORB mechanism, options-wrapper specific | T2 but **not transferable** — options-specific (0DTE decay, not applicable to spot gold) | — | — | — | — | — | not scored, wrong instrument |
| 15 | Fibonacci retracement bounce | Enter at 38.2/50/61.8% retracement of a prior swing | T3 (no source offered a real sample size or win rate at all) | 1 | 3 | 3 | 2 | low | 1.85 |
| 16 | ICT order block / FVG (Fair Value Gap) entries | Enter at institutional "order block" or gap-fill zones | T3 (definitionally vague — "order block" identification isn't a single testable rule across sources) | 1 | 2 (definition disagrees across sources — fails the hard_constraint that every rule be a concrete numeric test) | unknown | unknown | — | 1.40 |

*Score = 0.30×plausibility + 0.20×codeability + 0.15×signal-freq + 0.20×robustness + 0.15×independence, each sub-score out of 5, scaled. Candidates 12-16 given partial/no score where a sub-dimension wasn't determinable from available sources — flagged rather than guessed.

## Ranking reasoning (before the final table)

The T1/T2 tier splits cleanly from the T3 tier on one thing: **every T3 source
that stated a win rate stated a suspiciously round, high one (60%, 70%,
80%) with zero sample size, zero date range, and zero cost model.** That
pattern — a specific, attractive number with no way to check it — is
exactly what the spec's T3 definition warns about, and it shows up on
liquidity-sweep, Asian-range-fade, RSI mean-reversion, and Bollinger
band claims alike. The T1/T2 sources (the GitHub pullback-window repo, the
ORB Setups 190,000-trade study, our own gold_sweep_reversal.py backtest)
all report far less flattering, far more specific numbers: 52-55% win
rates, profit factors in the 1.6-2.0 range, and (in our own case) an
outright loss once real R:R was measured. I weighted plausibility and
robustness toward sources that could show their work, even when the
resulting win rate looked worse on paper — an unverifiable 80% is worth
less than a verifiable 55%.

Independence was the second filter. Candidates 1, 2, 3, and 4 fire on
different underlying beliefs (price is stretched and will revert; price is
trending and just shook out weak hands; the session's opening compressed
information and is now resolving; volatility itself is regime-switching)
and at different times relative to session structure (VWAP reversion needs
an already-extended session; ORB fires at the open; pullback-continuation
needs an established trend already in progress; volatility-squeeze fires
after a multi-bar compression that could occur any time). Candidate 5
(rolling-high/low breakout) was scored lower specifically because its
mechanism overlaps meaningfully with ORB — both are "trade the break of a
recent range" — so including both would not add real independence, just a
second implementation of the same underlying bet.

## Top 5 (ranked)

### 1. VWAP σ-Band Mean Reversion

**Mechanism:** Gold's intraday order flow is dominated by a relatively
small number of institutional executions benchmarked against VWAP. When
price stretches far enough from session VWAP without a strong trend behind
it, the stretch is more often inventory imbalance than new information, and
reverts.

**Market regime needed:** range/chop, NOT a strong trend day. Needs an
explicit trend filter to avoid firing on trend days (this is the single
biggest failure mode found in every source: "reversion fails badly on
trend days, and those failures dominate without a regime screen").

**Entry rule (pseudocode):**
```
1. Compute session VWAP and its rolling standard deviation (σ) from session open, M5 bars.
2. Compute ADX(14) on M15 bars as the trend filter.
3. IF ADX(14) < 20 (chop regime, default; range 15-25)
   AND close is beyond VWAP ± 2.0σ (default; range 1.5-2.5σ)
   AND the M5 bar that crossed 2.0σ closes back inside 2.0σ on the NEXT bar (confirmation, avoids catching a knife)
   THEN enter counter-trend, target = VWAP.
```

**Stop rule:** 1.0σ beyond the entry bar's extreme (default; range 0.75-1.5σ).
**Target rule:** session VWAP (full reversion) or 1.0σ (partial reversion) — test both.
**Scale-out:** move stop to breakeven once price has retraced 50% of the distance to VWAP.
**Invalidation:** ADX(14) crosses above 25 while the position is open — treat as a regime change, exit at market.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `vwap_sigma_entry` | 2.0 | 1.5-2.5 | Below 1.5σ is too common (low signal quality); above 2.5σ is too rare (underpowered) |
| `vwap_sigma_stop` | 1.0 | 0.75-1.5 | Needs to be tight enough that a real trend day is cut fast |
| `adx_chop_threshold` | 20 | 15-25 | Standard ADX chop/trend boundary in the literature found |
| `session_vwap_reset` | daily | fixed | VWAP must anchor at a real session boundary, not rolling |

**Expected failure mode:** a real trend day (e.g. a Fed/CPI surprise) where
price keeps extending past 2σ, 3σ, 4σ without reverting — the ADX filter is
the only defense and it lags.

**Evidence tier:** T2. [VWAP Trading Strategy (Backtest) – QuantifiedStrategies](https://www.quantifiedstrategies.com/vwap-trading-strategy/), [VWAP Standard Deviation Mean Reversion – FMZ](https://www.fmz.com/lang/en/strategy/474675), [VWAP reversion strategy – Crosstrade](https://crosstrade.io/learn/trading-strategies/vwap-reversion). Stated win rates (55-65%) are for ES/NQ/liquid futures with filters, not gold specifically — this is an honest gap, not a gold-specific number.

---

### 2. EMA-Trend Pullback + Breakout (4-Phase State Machine)

**Mechanism:** an established EMA-confirmed trend shakes out short-term
countertrend positions (a 1-3 bar pullback), then resumes; entering on the
breakout of the pullback's own extreme catches the resumption without
guessing the pullback's depth in advance.

**Market regime needed:** trending (opposite of #1 — this is the
independence argument in practice).

**Entry rule (pseudocode):**
```
1. SCANNING: monitor for a fast-EMA/slow-EMA crossover (defaults: EMA(9)/EMA(21) on M5) plus directional confirmation (close beyond both EMAs).
2. ARMED: once trend direction is set, wait for 1-3 consecutive counter-trend M5 candles (a pullback).
3. WINDOW_OPEN: mark the pullback's own high (if trend is down) or low (if trend is up) as the breakout trigger.
4. ENTRY: enter on a confirmed break of that level in the trend direction.
```

**Stop rule:** 2.5x ATR(14) from entry (source-stated default).
**Target rule:** 12.0x ATR(14) from entry (source-stated default — a wide target relative to the stop, R:R ≈ 4.8:1 nominal; real R:R needs re-verification against realized ATR, not assumed, the exact mistake found in our own sweep-reversal work).
**Invalidation:** if price re-crosses back through both EMAs before the breakout triggers, the setup is void (trend has failed, not just paused).

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `ema_fast` | 9 | 5-15 | Standard fast-EMA range |
| `ema_slow` | 21 | 15-34 | Standard slow-EMA range |
| `pullback_max_bars` | 3 | 1-5 | Source states "1-3 counter-trend candles"; wider risks catching a real reversal instead of a pullback |
| `stop_atr_mult` | 2.5 | 1.5-3.5 | Source-stated default |
| `target_atr_mult` | 12.0 | 6.0-15.0 | Source-stated default — **flagged as the single most suspicious number in this whole shortlist**, needs its own re-verification given our own R:R-collapse experience |

**Expected failure mode:** choppy, non-trending markets — no clean EMA
crossover ever forms, or forms and immediately fails, generating whipsaw
losses at the stop.

**Evidence tier:** T1/T2 — real open-source code with a real, gold-specific,
5-year backtest: 175 trades, July 2020-July 2025, Sharpe 0.892, profit
factor 1.64, win rate 55.43% (97W/78L), max drawdown 5.81%, total return
+44.75%. [ilahuerta-IA/backtrader-pullback-window-xauusd](https://github.com/ilahuerta-IA/backtrader-pullback-window-xauusd). **Caveat found, not hidden:** no stated in-sample/out-of-sample split — the entire 5-year period appears to be one continuous backtest, so this number carries real overfitting risk until P3's walk-forward protocol re-tests it properly.

---

### 3. Session Opening-Range Breakout (ORB)

**Mechanism:** the first N minutes of a session compress overnight/pre-open
order flow into a tight range; the initial break of that range captures
the market's first real directional resolution of the day, before slower
participants have caught up.

**Market regime needed:** session-open volatility expansion — works
regardless of the day's eventual trend/range character, since it only
needs to catch the *initial* move.

**Entry rule (pseudocode):**
```
1. Mark the high/low of the first 15 minutes after session open (default; range 5-60 min) — use the London open (07:00 UTC) as the primary session, per this repo's own Gold Sweep-Reversal card.
2. IF an M5 candle closes beyond the opening-range high/low
   THEN enter in the breakout direction at that close.
3. Only the FIRST breakout of the day counts — ignore re-breaks of the same level.
```

**Stop rule:** opposite side of the opening range (i.e. the range itself is the stop distance).
**Target rule:** 1x the opening-range width, measured from the breakout point (a "measured move" target — default; range 0.75x-2.0x).
**Invalidation:** if price closes back inside the opening range after the breakout, exit — the breakout has failed.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `or_minutes` | 15 | 5-60 | Standard ORB range; shorter is noisier, longer risks missing the actual move |
| `target_multiple` | 1.0x range | 0.75x-2.0x | Measured-move convention; needs its own re-verification (see honesty_clause) |
| `session_open_utc` | 07:00 (London) | 07:00 / 13:00 (NY) / 00:00 (Asia) | This repo's own analysis already found London and NY-overlap are the "good"/"best" sessions for gold, Asia is worst |

**Expected failure mode:** a session that opens directly into a strong
pre-existing trend with no real compression — the "opening range" is
arbitrary and gets swept immediately in both directions (whipsaw).

**Evidence tier:** T2. Large-sample general-market study: 190,000+ trades
across 611 stocks/ETFs, 52.2-52.9% win rate depending on ORB window,
expectancy +0.004R to +0.028R — genuinely thin edge before gold-specific
adjustment. [ORB Setups research](https://orbsetups.com/research/opening-range-breakout-win-rate/). A separate, smaller, more favorable study: 198 trades, 65% win rate, profit factor 2 — [QuantifiedStrategies ORB backtest](https://www.quantifiedstrategies.com/opening-range-breakout-strategy/), though that source also states plainly "opening range breakout trading strategies don't work very well anymore." **Both numbers are real; they disagree, and that disagreement is itself the honest finding — this needs its own P3 re-test on gold specifically, not an assumed number from either source.**

---

### 4. ATR/Keltner Volatility-Squeeze Breakout

**Mechanism:** volatility clustering (low-volatility periods tend to be
followed by continued low volatility, until a regime shift produces
continued high volatility) is one of the most robustly documented
statistical properties of financial time series in the broader academic
literature — even though the *specific parameterized trading rule* below
has no rigorous published gold backtest. Trade the expansion that follows
a measured compression.

**Market regime needed:** post-compression regime shift — genuinely
different timing condition from #1 (needs an extended stretch), #2 (needs
an established trend), and #3 (fires only at session open).

**Entry rule (pseudocode):**
```
1. Compute Bollinger Band width (20, 2.0) and its 100-bar percentile rank, M5.
2. IF BB-width percentile < 10th percentile (a "squeeze"; default, range 5th-20th)
   for at least 6 consecutive M5 bars (default; range 3-12 bars)
3. THEN arm the setup: mark the high/low of the squeeze window.
4. ENTRY: on the first M5 close beyond the squeeze window's high/low.
```

**Stop rule:** 1.0x ATR(14) inside the squeeze base (i.e. re-entry into the compression zone invalidates the breakout).
**Target rule:** trail with a 2.0x ATR(14) chandelier stop rather than a fixed target — this mechanism is about capturing the size of the expansion, not a fixed measured move.
**Invalidation:** BB-width percentile re-enters the squeeze zone before the breakout triggers.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `bb_width_percentile` | 10th | 5th-20th | Tighter = rarer but higher-quality squeezes |
| `squeeze_min_bars` | 6 | 3-12 | Needs enough bars to be a real compression, not noise |
| `trail_atr_mult` | 2.0 | 1.5-3.0 | Standard chandelier-exit convention |

**Expected failure mode:** a false squeeze breakout that immediately fails
and reverses (the compression resolves in a whipsaw rather than a clean
expansion) — this is explicitly called out by multiple sources as the
main risk, and no source offered a real mitigation beyond "use it
cautiously around news."

**Evidence tier: T3, explicitly flagged per the spec's own instruction.**
Every specific-strategy source found was blog-tier (Medium, TradingView
descriptions) with no stated sample size or win rate for gold specifically.
**Included anyway because the underlying mechanism — volatility
clustering/regime persistence — has real, independent academic support as
a general market property**, not because any specific backtest of this
rule checks out. [ATR Channel Squeeze Breakout – FMZQuant](https://medium.com/@FMZQuant/atr-channel-squeeze-breakout-strategy-volatility-breakout-trading-system-with-momentum-indicator-be10b8784ee9), [Volatility Squeeze Breakout with ADX/ATR – PyQuantLab](https://pyquantlab.medium.com/volatility-squeeze-breakout-strategy-with-adx-and-atr-trailing-stops-40a3a787212b).

---

### 5. Rolling High/Low Breakout with ADX/EMA Trend Filter

**Mechanism:** distinct from ORB (#3) in that the reference range is a
*rolling* lookback (e.g. the last 24 hours), not a fixed session-open
window — this catches breakouts of any multi-session consolidation, not
just the day's own open. Filtered by trend strength/direction so it only
fires when a real directional move is statistically more likely.

**Market regime needed:** a multi-session consolidation resolving into a
trend — different timing profile from ORB (session-open-specific) even
though both are "breakout of a range" in spirit.

**Entry rule (pseudocode):**
```
1. Compute rolling 24-hour (288 M5-bar) high/low.
2. Compute ADX(14) and EMA(50) slope on M15 as trend filters.
3. IF close breaks the rolling 24h high AND EMA(50) slope is positive AND ADX(14) > 20
   THEN enter long (mirror for short).
```

**Stop rule:** trailing stop, source states "pure trailing stop exit" (exact multiple not independently re-verified by me).
**Target rule:** none fixed — ride the trailing stop.
**Invalidation:** ADX(14) drops back below 15 (trend has weakened before the trailing stop caught it).

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `lookback_hours` | 24 | 12-48 | Source uses 24h; range covers shorter/longer consolidation windows |
| `adx_trend_threshold` | 20 | 15-25 | Same convention as candidate #1's chop threshold, opposite direction |

**Expected failure mode:** a rolling-high/low breakout that fires
concurrently with an ORB signal in the same direction (since both are
range-breakout mechanisms) — **this is the honesty point on independence**:
this candidate is the weakest of the 5 on that dimension, included for
completeness of the "trend-confirmation-gated breakout" mechanism family
rather than because it's clearly non-overlapping with #3.

**Evidence tier:** T2 — open source with stated brute-force parameter-scan
tooling, but I could not independently re-verify its exact win-rate/profit-factor
numbers from the README alone (would need to actually run the repo's own
backtest, which is P2/P3's job, not P1's). [doaneruby970-hub/gold-trader (V8 Breakout-Tracking EA)](https://github.com/doaneruby970-hub/gold-trader).

## Mechanisms I rejected and why

**Liquidity sweep / stop-hunt reversal (ICT/SMC).** Already covered above
in detail — excluded specifically because it's the mechanism this repo's
own `gold_sweep_reversal.py` already tested rigorously (6 months real data,
160+ parameter combinations) and found net-negative, contradicting every
T3 win-rate claim found for it externally.

**RSI(M5) overbought/oversold fade.** One source stated plainly "a
reversion robot trading five-minute XAUUSD bars is betting on a pattern no
study has confirmed at that timescale" — an honest admission from within
the practitioner literature itself that this doesn't have real intraday
evidence at M5.

**Bollinger Band breakout/reversion (as a single mechanism).** Rejected for
being definitionally ambiguous across sources — some describe fading band
touches (mean reversion), others describe trading band breaks (momentum).
A strategy that can't even agree with itself on direction fails the
"binary and testable" anti-pattern rule outright.

**Asian-range fade ("Goldmine Strategy").** The single most aggressive
claim found in this entire search (80% win rate, "backtested over
thousands of trades") with zero methodology, zero date range, and
marketing-style delivery (a branded name, a Medium blog series) — the
textbook T3 profile the spec warns about.

**Pin-bar/candlestick reversal, Fibonacci retracement, ICT order
blocks/FVG.** All T3, all lacking any stated sample size, and in the case
of order blocks/FVG, lacking even a single consistent testable definition
across sources — rejected on the hard_constraint that every rule must be
numerically concrete, not just the evidence-tier grounds.

**Chinese gold/silver futures "night effect" and academic TS-momentum via
realized semivariance.** Both are real, peer-reviewed (T1) findings, but
rejected for transferability: the former is tied to Chinese futures
market-specific session/settlement structure that doesn't map onto XAUUSD
spot/CFD trading, and the latter is designed for daily/multi-day momentum
horizons, not a 2-8-signals-per-day scalping frequency — including either
without real adaptation work would be dressing up a different problem as
this one.
