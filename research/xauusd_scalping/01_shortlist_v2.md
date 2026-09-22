# XAUUSD Scalping — Strategy Landscape Sweep v2 (price-action / liquidity focus)

## What changed from v1, and why

The first pass (`01_shortlist.md`) shortlisted VWAP σ-bands, EMA pullback,
opening-range breakout, ATR/Keltner squeeze, and rolling high/low breakout —
all indicator-first mechanisms (VWAP, EMA, ADX, ATR, Bollinger drive the
entry directly). Rakesh's feedback: he wants **price action and
institutional-liquidity concepts leading**, with indicators used only for a
**confidence score**, the same informational-not-a-gate shape this repo's
own `_confidence_score()` in `strategies/gold_sweep_reversal.py` already
uses (SL-width, reclaim-speed, and loss-streak inputs, appended to the
reasoning text, never blocking an entry) — not thrown out entirely, just
demoted from primary trigger to confirmation layer. He also asked to find
"the algo big institutions use."

**Honest framing on that last point, stated plainly rather than overclaimed:**
real bank/prop-desk execution algorithms (VWAP/TWAP execution slicing,
market-making, HFT) are proprietary and not published anywhere verifiable.
The closest legitimate, *testable* public proxy is retail-facing "Smart
Money Concepts" (SMC) / ICT methodology, which claims to reverse-engineer
institutional order-flow behavior (liquidity grabs, order blocks, fair
value gaps) — but as this search confirmed repeatedly, most of that
literature is marketing-tier (T3): suspiciously round win rates (64%, 70%,
75%, 80%) with no sample size, no date range, no cost model, often
attached to a paid course or signal service. The honest goal here is **to
rigorously backtest the SMC/price-action claims that are actually
testable**, not to claim access to confirmed institutional algorithms.

This pass evaluated 20 candidates (up from 16) and shortlists 10 (up from
5), all led by a price-action/market-structure trigger, each with an
explicit indicator-based confidence layer, and — critically — checked each
liquidity-adjacent candidate against whether it's just a repaint of the
rule this repo's own `gold_sweep_reversal.py` already tested and falsified
(6 months real data, 201 trades, 47.8% win rate, net -$12,705.76, real R:R
collapsed to ~0.46:1 vs. the assumed 2.5:1; then 160+ parameter-sweep
combinations across session window, level richness, and SL/TP all also
came back net-negative — `docs/strategies/gold-xauusd-sweep-reversal.md`
§3). Two candidates below (#1, #9) are liquidity-sweep variants; both are
flagged with an explicit "how this differs from the falsified rule"
note — neither is included as a bare repaint.

## Candidates evaluated (20 total, before narrowing to 10)

| # | Candidate | Primary trigger | Evidence tier | Notes |
|---|---|---|---|---|
| 1 | Liquidity sweep + displacement + FVG retest | price action | T3 (no verifiable stats for this exact sequence) | Differs from falsified rule — see card |
| 2 | Multi-timeframe liquidity alignment (HTF pool + LTF CHoCH) | price action | T2/T3 mixed | Differs from falsified rule — see card |
| 3 | Order block retest after BOS | price action | T3 (blog-tier claims: 50-77% WR, no sample size) | — |
| 4 | Wyckoff spring/upthrust at range extremes | price action | T2 (established classical methodology, no intraday gold backtest found) | — |
| 5 | NR7/inside-bar compression breakout | price action (volatility-cycle, non-SMC) | T1/T2 (Crabel's original research is real and cited; no gold-specific intraday stats found) | — |
| 6 | Premium/discount OTE Fibonacci retracement | price action | T3 (zero backtest evidence found anywhere, but the rule is numerically concrete) | — |
| 7 | Market Profile value-area rotation (fade VAH/VAL to POC) | price action (non-SMC, classical futures-desk methodology) | T2 (real professional lineage — Steidlmayer/CBOT — no gold-specific numbers found) | — |
| 8 | Break-of-structure pullback continuation | price action | T3 (definitional-only sources, no backtest data found for BOS/CHoCH anywhere) | — |
| 9 | Session liquidity run + reversal into opposing pool | price action | T3 | Differs from falsified rule — see card |
| 10 | Equal highs/lows sweep + RSI divergence (hard-gated) | price action + indicator co-trigger | T3 (mechanism sourced from ICT/SMC liquidity literature; RSI-divergence-as-gate is my own addition, not sourced) | Indicator is a REQUIRED gate here, not just confidence — see card |
| 11 | Volume delta / footprint absorption | order flow | — | **Rejected — hard constraint violation, see below** |
| 12 | Bare liquidity sweep, return-to-sweep-point exit (ikeawesom GitHub) | price action | T2 (real open-source, real stated results: 2004-2024, 15m, 4547 trades, 71.17% WR — but no PF/drawdown given) | **Rejected — too close to the falsified rule, see below** |
| 13 | Harmonic patterns (Gartley/Bat/Butterfly) | price action | T3, and largely subjective pattern-recognition | Rejected, see below |
| 14 | Elliott Wave counting | price action | none (fails hard_constraint: not a single testable rule) | Rejected |
| 15 | Generic candlestick reversal (pin bar) at S/R | price action | T3 (carried over from v1, still rejected) | Rejected |
| 16 | Generic support/resistance bounce | price action | T3, definitionally vague | Rejected (fails v1's own anti-pattern rule) |
| 17 | FVG same-session mitigation rate (Edgeful) | price action (statistical property, not a strategy) | T2 for the raw stat (well-defined "by close" methodology, YM futures), T3 for any trading application | Used as an input to #1's confidence layer, not a standalone candidate |
| 18 | "Unfiltered SMC" baseline (FXNX backtest claim) | price action | T3 (1,000-trade claim, no dates, no PF, no consistent spread) but self-critical (reports 38-45% WR, not a flattering number) | Used as a calibration data point, not a standalone candidate |
| 19 | Quantum Algo SMC order-block claims (64.2%/75% WR, 2.3R) | price action | T3 — textbook red-flag pattern (round numbers, no sample size, no date range) | Rejected as a standalone source; folds into #3's honest evidence-tier note |
| 20 | Wyckoff strategy backtest (QuantifiedStrategies) | price action | Referenced but not independently fetched/verified this pass — noted, not relied on | Folds into #4 |

## Rejected mechanisms and why

**Volume delta / footprint / order-flow absorption.** Genuinely
institutional-grade methodology with real practitioner support, but it
**requires real bid/ask tick-level order-flow data**, which the P1 spec's
own hard_constraint explicitly excludes ("No order flow, no L2 depth, no
tick-volume-derived 'real volume'"). Rejected on a hard constraint, not a
quality judgment — this is likely closer to genuine institutional
methodology than anything else found in this search, but it's not
buildable from OHLCV alone with the data this repo actually has access to.

**Bare liquidity sweep, return-to-sweep-point exit (ikeawesom GitHub).**
Real, reproducible open-source code with real stated results — but the
mechanism (sweep PDH/PDL, reverse, target = return to the swept level) is
**functionally identical** to `gold_sweep_reversal.py`'s already-falsified
rule: same trigger (a session/day-level sweep), same reversal logic, and a
similarly tight target relative to the wick-extreme-driven stop — exactly
the R:R shape that collapsed in our own backtest. Including it as a
separate candidate would risk re-litigating the same falsified rule under
a different name. (Candidate #1 below takes the same starting point but
changes the mechanism meaningfully — see its own differentiation note.)

**Harmonic patterns, Elliott Wave, generic pin-bar/S-R bounce.** All T3 or
worse, and each fails the hard_constraint that every rule be concretely
numeric and binary — harmonic pattern recognition and Elliott wave counts
in particular require subjective judgment calls that can't be reduced to a
deterministic function of OHLCV without a lot of unstated interpretation.

## Top 10 (ranked)

### 1. Liquidity Sweep + Displacement + FVG Retest

**Mechanism:** price sweeps a marked liquidity level (session/day high or
low), an aggressive displacement candle immediately follows in the
opposite direction (a large-bodied candle closing near its extreme, not
just "closing back inside"), and entry is on the retest of the Fair Value
Gap that displacement candle left behind — not at the bare reclaim close.

**How this differs from the falsified rule (not a repaint):**
`gold_sweep_reversal.py` enters at the close of the very next candle that
closes back inside the level, with no requirement that the reclaim be
forceful. This candidate requires (a) a genuinely aggressive displacement
candle as confirmation the sweep was real, not noise, and (b) a retest
entry at the FVG rather than the reclaim close itself — a materially
better, more precise entry price than "wherever the reclaim candle
happened to close," which is plausibly a meaningful chunk of the R:R
collapse the original rule suffered from.

**Market regime needed:** any session with real volatility (Asian chop is
explicitly the worst per this repo's own session-window sweep finding —
carry that forward, don't retest Asian).

**Entry rule (pseudocode):**
```
1. Mark session/day high/low levels (reuse this repo's existing Asian High/Low, PD High/Low).
2. IF price trades beyond a level (the sweep)
3. AND the very next M5 candle is a displacement candle: body >= 1.5x the 20-bar average body size (default; range 1.2-2.0x), closing in the top/bottom 25% of its own range, in the reversal direction
4. THEN mark the FVG: the 3-candle gap between the sweep candle and the candle after the displacement candle (if one exists), or the displacement candle's own body if no clean 3-candle gap forms
5. ENTRY: on a retest (touch, not necessarily close) of that FVG zone, in the reversal direction.
```

**Stop rule:** beyond the sweep's wick extreme + buffer (same formula as
`gold_sweep_reversal.py`, `min_sl_pts`/`sl_buffer_pts` reused).
**Target rule:** the opposing liquidity pool (the next marked level in the
opposite direction), not a fixed point value — this is the single biggest
structural difference from the falsified rule, whose fixed 7.5pt target
was mismatched to its own realized SL width.
**Invalidation:** FVG is fully filled (price trades all the way through it)
without triggering entry — the setup is void, don't chase.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `displacement_body_mult` | 1.5x avg body | 1.2-2.0x | Below 1.2x risks false displacement; above 2.0x is too rare |
| `displacement_close_pct` | top/bottom 25% | 10-35% | How close to the extreme the candle must close to count as forceful |
| `fvg_fill_invalidation` | 100% (full fill) | 75-100% | Whether a partial fill still allows entry |

**Confidence/confirmation layer** (informational, never a hard gate — same
shape as `_confidence_score()`): ATR-normalized sweep depth (how far past
the level price went, relative to ATR(14) — a deeper sweep with strong
displacement is more convincing than a shallow poke), RSI(14) divergence
at the sweep extreme (price makes a new extreme, RSI doesn't — classic
exhaustion signature), and the existing loss-streak component already
built.

**Expected failure mode:** a genuine trend day where the "sweep" is
actually the market moving on, not stopping out weak hands — the
displacement filter helps but doesn't eliminate this.

**Evidence tier:** T3 for this exact sequence (no verifiable win rate/PF
found for "sweep + displacement + FVG retest" as a single combined rule —
every source describing it is marketing/educational content with zero
stated sample size, e.g. [tradelikemaster.com's gold scalping guide](https://tradelikemaster.com/blog/gold-scalping-strategy-2026)). The
component parts have mixed evidence: FVG same-session mitigation rates
(60-63%) are a real, well-defined statistic from [Edgeful](https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide), but that's a
gap-fill-rate stat, not a P&L backtest.

---

### 2. Multi-Timeframe Liquidity Alignment (HTF Pool + LTF CHoCH)

**Mechanism:** trades a liquidity pool marked on a HIGHER timeframe
(daily/weekly equal highs or lows, or the prior week's high/low) only once
a LOWER-timeframe Change of Character confirms the reversal has actually
started — a two-tier confirmation structure, not a single-bar reclaim.

**How this differs from the falsified rule:** the falsified rule uses only
same-day/prior-day levels on the same M5 timeframe as the entry. This
candidate requires the swept level to be a genuinely higher-timeframe
liquidity pool (multi-day/weekly significance, defined as: two or more
daily highs/lows within 0.15% of each other in the last 10 trading days —
"equal highs/lows"), and requires a structural shift on the entry
timeframe (a CHoCH: the first M5 swing point broken against the prior
trend) before entering, not just a single-candle close-back.

**Market regime needed:** works best after an extended run in one
direction that has built up genuine multi-day liquidity above/below it.

**Entry rule (pseudocode):**
```
1. Scan the last 10 trading days for equal highs/lows: two or more daily H (or L) within 0.15% of each other (default; range 0.10-0.25%).
2. IF price sweeps that HTF pool
3. AND the M5 chart prints a CHoCH: the most recent minor swing point in the pre-sweep trend direction is broken
4. THEN enter in the CHoCH direction at the break.
```

**Stop rule:** beyond the HTF sweep's wick extreme.
**Target rule:** the next HTF liquidity pool in the opposite direction.
**Invalidation:** price re-takes the sweep extreme before the CHoCH
confirms — the setup never triggers, no entry.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `equal_level_tolerance_pct` | 0.15% | 0.10-0.25% | How close two daily extremes must be to count as "equal" |
| `htf_lookback_days` | 10 | 5-20 | How far back to scan for equal highs/lows |
| `choch_swing_lookback` | 3 bars | 2-5 | Minimum bars either side to confirm a swing point on M5 |

**Confidence/confirmation layer:** ADX(14) on the HTF (daily) to confirm
the prior move that built the liquidity was a real trend, not chop; volume
(where available)/ATR expansion on the sweep bar itself.

**Expected failure mode:** false CHoCH signals in choppy conditions where
minor swing points break constantly without a real structural shift.

**Evidence tier:** T2/T3 mixed — BOS/CHoCH definitions themselves are
well-documented across many sources ([Alchemy Markets](https://alchemymarkets.com/education/strategies/break-of-structure-bos-trading/), [Inner Circle Trader](https://innercircletrader.net/tutorials/break-of-structure-vs-change-of-character/)) but **no source found gives quantified
backtest performance** for BOS/CHoCH-based entries specifically — this is
an honest gap, not a hidden one.

---

### 3. Order Block Retest After BOS

**Mechanism:** the last opposing-color candle before a decisive Break of
Structure is the "order block" — the theory being it marks where large
players' remaining orders sit. Trade the first retest of that candle's
range after the BOS confirms.

**Market regime needed:** trending, post-BOS continuation.

**Entry rule (pseudocode):**
```
1. IF price breaks a prior significant swing high/low with a decisive close (BOS confirmed: close beyond the swing point by >= 0.3x ATR(14), default; range 0.1-0.5x)
2. THEN mark the last opposite-color candle before the impulse leg that caused the BOS as the order block.
3. ENTRY: on the first retest (touch) of that candle's body range, in the BOS direction.
```

**Stop rule:** beyond the order block's own extreme.
**Target rule:** 2x the distance from entry to the BOS point (measured-move convention; range 1.5x-3.0x).
**Invalidation:** price closes through the order block's far side without reversing — the block has failed, exit.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `bos_decisive_close_atr_mult` | 0.3x ATR | 0.1-0.5x | How far past the swing point the close must be to count as decisive, not a wick poke |
| `target_measured_move_mult` | 2.0x | 1.5-3.0x | — |

**Confidence/confirmation layer:** ADX(14) rising (trend strength
increasing into the BOS), EMA(20/50) alignment with the BOS direction.

**Expected failure mode:** the order block is retested and blown through
cleanly (a common SMC criticism — "order blocks" are a retrospective
labeling exercise with no guarantee the original orders are still there).

**Evidence tier:** T3. Every specific win-rate claim found for order
blocks (50-77%, [SiyabongaDlamini/SmartMoney.MQ5](https://github.com/SiyabongaDlamini/SmartMoney.MQ5), [Quantum Algo](https://www.quantum-algo.com/blog/best-indicator-xauusd-gold/)) is
either a code-repo description with no independently-verified backtest run,
or a blog claim with no stated sample size/date range — one honest
counter-data-point found: "unfiltered, rules-based SMC setups yield win
rates hovering between 38% and 48%, accompanied by double-digit losing
streaks" ([FXNX](https://fxnx.com/en/blog/smart-money-concepts-work-backtest-evidence)), which is far less flattering and, being self-critical, more
credible than the round high numbers.

---

### 4. Wyckoff Spring / Upthrust at Range Extremes

**Mechanism:** a multi-day trading range (accumulation or distribution) has
its extreme swept by a "spring" (false breakdown) or "upthrust" (false
breakout) that immediately reverses — a genuinely different setup from a
single-session sweep because it requires an established, multi-day RANGE
first, not just a prior-day/session high-low pair.

**Market regime needed:** an actual multi-day consolidation range must
exist first — this strategy sits out trending markets entirely by
construction.

**Entry rule (pseudocode):**
```
1. Detect a range: N trading days (default 5, range 3-10) where each day's high/low stays within X% (default 1.5%, range 1.0-2.5%) of the range's own overall high/low.
2. IF price sweeps beyond the range extreme (the spring/upthrust)
3. AND closes back inside the range within the same or next M5 bar
4. THEN enter in the reversal direction, targeting the opposite side of the range.
```

**Stop rule:** beyond the spring/upthrust wick extreme.
**Target rule:** the opposite side of the established range (the range's
own height, not a fixed point value).
**Invalidation:** price closes beyond the range extreme by more than the
spring/upthrust's own depth on a subsequent bar — the range has genuinely
broken, not sprung.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `range_min_days` | 5 | 3-10 | Minimum days to call it a real range, not noise |
| `range_tolerance_pct` | 1.5% | 1.0-2.5% | How tightly bounded the range must be |

**Confidence/confirmation layer:** ATR contraction during the range
(confirms genuine compression, not just sideways chop with high
volatility); the existing loss-streak component.

**Expected failure mode:** a range that isn't a real accumulation/
distribution structure at all, just directionless chop — springs/upthrusts
in genuine chop have no statistical edge, the Wyckoff literature's own
caveat.

**Evidence tier:** T2 for the underlying methodology (Wyckoff's original
work and its modern treatments — [TrendSpider](https://trendspider.com/learning-center/chart-patterns-wyckoff-accumulation/), [Wyckoff Analytics](https://www.wyckoffanalytics.com/wyckoff-method/) — are
well-established, not marketing-tier); no intraday-gold-specific backtest
numbers were found in this search, an honest gap. A QuantifiedStrategies
page titled "Wyckoff Trading Strategy — Backtest Results" exists but
wasn't independently fetched this pass — noted as a lead for P3, not relied
on here.

---

### 5. NR7 / Inside-Bar Compression Breakout

**Mechanism:** the single genuinely non-SMC, non-liquidity candidate on
this list, included specifically for mechanism independence. A bar with
the narrowest range in the last 7 bars (NR7), especially compounded with
an inside bar (fully contained within the prior bar's range), signals
volatility compression that historically precedes expansion (Toby Crabel's
original research, well-cited across the technical analysis literature).

**Market regime needed:** works regardless of trend/range — it's a
volatility-cycle mechanism, orthogonal to direction.

**Entry rule (pseudocode):**
```
1. Compute each M15 bar's range (high - low).
2. IF the current bar's range is the smallest of the last 7 bars (NR7)
   AND the current bar is also an inside bar (high <= prior high, low >= prior low)
3. THEN enter on the first M5 close beyond the NR7/inside bar's own high or low, in the breakout direction.
```

**Stop rule:** opposite side of the NR7/inside bar.
**Target rule:** 1.5x the NR7 bar's own range (measured move; range 1.0x-2.5x).
**Invalidation:** price closes back inside the NR7 bar's range after the breakout — failed breakout, exit.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `nr_lookback` | 7 | 5-10 | Standard NR7 convention |
| `target_range_mult` | 1.5x | 1.0-2.5x | — |

**Confidence/confirmation layer:** ATR percentile rank (confirms this is a
genuine multi-bar compression, not just one quiet bar), ADX for
post-breakout follow-through likelihood.

**Expected failure mode:** a false breakout that immediately reverses — the
single most commonly cited risk for any compression-breakout mechanism.

**Evidence tier:** T1/T2 for the underlying NR7 concept (Crabel's original
work is real, cited research, not blog-tier — [LuxAlgo](https://www.luxalgo.com/library/concept/nr4-nr7-narrow-range-bars/), [StrategyQuant](https://strategyquant.com/blog/inside-bar-breakout-strategy-price-action-trading/)); no
gold-specific intraday backtest numbers were found in this search, an
honest gap to fill in P3.

---

### 6. Premium/Discount OTE Fibonacci Retracement

**Mechanism:** once a higher-timeframe directional bias is established,
only take entries in the "discount" zone (buying) or "premium" zone
(selling) of the most recent significant swing — specifically the 61.8%-79%
retracement zone ICT literature calls "Optimal Trade Entry" (OTE).

**Market regime needed:** an established directional bias on a higher
timeframe (H1/H4) — this is a pullback-entry-timing tool, not a
standalone directional signal.

**Entry rule (pseudocode):**
```
1. Establish HTF bias (H1 EMA(50) slope direction, or the most recent HTF BOS direction).
2. Mark the most recent significant swing (a move of >= 1.5x ATR(14) H1, default; range 1.0-2.5x).
3. Compute the 61.8%-79% retracement zone of that swing (default OTE zone; the 70.5% level is the commonly-cited "optimal" point within it).
4. ENTRY: on a confirmed reaction (an M5 close back in the bias direction) within that zone.
```

**Stop rule:** beyond the 79%+ level (i.e. beyond the zone, invalidating the swing).
**Target rule:** the swing's own origin (a full retracement-reversal), or 1x the swing's length (range 0.75x-1.5x).
**Invalidation:** price closes beyond the 79% level without reacting — the OTE zone failed, the swing's significance is in question.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `ote_zone_low` | 61.8% | 50-65% | Standard Fibonacci convention |
| `ote_zone_high` | 79% | 75-88.6% | ICT's own stated upper bound |
| `min_swing_atr_mult` | 1.5x | 1.0-2.5x | Minimum swing size to bother marking an OTE zone for |

**Confidence/confirmation layer:** RSI(14) — is momentum actually
supportive of a continuation in the bias direction, not just a mechanical
retracement; number of prior touches of the same zone (fresher zones
should be weighted higher, in the same "informational, not a gate" spirit
as the rest of this list).

**Expected failure mode:** a genuine trend reversal, not a pullback — the
swing that looked significant turns out to be the start of a new opposite
trend, and the "discount"/"premium" zone is on the wrong side entirely.

**Evidence tier:** T3 — the rule itself is numerically concrete (a real
strength, satisfies the hard_constraint cleanly) but **zero backtest
evidence was found anywhere** for OTE specifically, across [ChartingLens](https://chartinglens.com/blog/ict-optimal-trade-entry-ote), [Backtrex](https://backtrex.com/en/blog/ict-optimal-trade-entry-ote-fibonacci-guide), [Inner Circle Trader](https://innercircletrader.net/tutorials/ict-fibonacci-levels/), and
others — every source is purely educational. This is one of the more
interesting gaps in the whole search: a very widely-taught rule that
apparently nobody has published real numbers for.

---

### 7. Market Profile Value-Area Rotation

**Mechanism:** the one candidate drawn from classical futures-desk
methodology (Peter Steidlmayer's original CBOT work, not the newer SMC/ICT
family) — on a "rotational" (non-trend) day, price tends to oscillate
within the prior day's Value Area (the price band containing ~70% of
volume/time), and fading the Value Area High/Low back toward the Point of
Control (the single most-traded price) is a well-established professional
concept.

**Market regime needed:** explicitly a range/rotation day, not a trend day
— needs a day-type classifier (see confidence layer) to avoid firing on
trend days, the same core weakness candidate #1 in v1 (VWAP mean
reversion) had.

**Entry rule (pseudocode):**
```
1. Compute yesterday's Value Area High (VAH), Value Area Low (VAL), and Point of Control (POC) from a volume-at-price (or time-at-price, if real volume isn't reliable) distribution.
2. IF today's session opens inside yesterday's Value Area (a "balance" day signal)
3. AND price reaches VAH or VAL
4. THEN fade back toward POC.
```

**Stop rule:** just beyond VAH/VAL (the level being faded).
**Target rule:** POC (full rotation) or the Value Area's own midpoint (partial).
**Invalidation:** price closes beyond VAH/VAL by more than a buffer — this is a trend day forming, not a rotation day, stand aside.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `open_inside_value_required` | true | true/false | Whether to require the balance-day precondition strictly |
| `stop_buffer_pts` | TBD from ATR | — | Needs real data to calibrate, not guessed |

**Confidence/confirmation layer:** ADX(14) (low ADX supports the rotation
premise, same logic as v1's VWAP candidate); how many consecutive prior
days have also opened inside value (a genuine balance regime vs. a
one-off).

**Expected failure mode:** identical to v1's VWAP mean-reversion candidate
— a trend day where the regime filter fails to catch the shift in time.

**Evidence tier:** T2 for the general professional methodology (real
lineage, used by real futures desks — [Bookmap](https://bookmap.com/blog/market-profile-trading-understanding-its-power-and-impact), [TradersPost](https://blog.traderspost.io/article/market-profile-trading-strategies)); no
gold-CFD-specific backtest numbers found (real volume isn't reliably
available for OTC/CFD gold the way it is for exchange-traded futures — an
honest data-availability caveat that P2/P3 will need to address directly).

---

### 8. Break-of-Structure Pullback Continuation

**Mechanism:** the trend-following counterpart to #2/#3's reversal-focused
candidates — once a Break of Structure confirms a trend is intact/renewed,
trade a shallow pullback continuation in the trend direction, rather than
fading anything.

**Market regime needed:** trending — deliberately the opposite regime bet
from #1, #4, #7 (independence argument).

**Entry rule (pseudocode):**
```
1. IF a BOS confirms (per candidate #3's definition)
2. AND price pulls back no more than 38.2% of the BOS impulse leg (default; range 23.6-50%)
3. THEN enter in the BOS direction on the pullback's own low/high being broken (continuation confirmation).
```

**Stop rule:** beyond the pullback's own extreme.
**Target rule:** measured move (1x the BOS impulse leg length; range 0.75x-1.5x).
**Invalidation:** pullback exceeds 50% of the impulse leg — too deep to call a pullback, the trend may be exhausted.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `max_pullback_pct` | 38.2% | 23.6-50% | Fibonacci-convention pullback depth cap |

**Confidence/confirmation layer:** EMA(9/21) slope alignment (both EMAs
sloping in the trend direction confirms momentum is genuinely intact, not
just a single impulsive bar), ADX(14) rising.

**Expected failure mode:** a BOS that turns out to be a liquidity grab
itself (a "fakeout BOS") rather than a genuine trend continuation — the
SMC literature's own most commonly cited failure mode for this family of
setups.

**Evidence tier:** T3 — same gap as #2 and #3: BOS/CHoCH concepts are
extensively documented, but no source found gives quantified backtest
performance for a BOS-based continuation entry specifically.

---

### 9. Session Liquidity Run + Reversal into Opposing Pool

**Mechanism:** distinct from a single-level sweep — this requires an
initial session to have "run" through MULTIPLE liquidity levels in one
direction (not just poked one level), then fades back targeting the
UNTOUCHED opposing session's liquidity pool specifically, not just the
local sweep origin.

**How this differs from the falsified rule:** `gold_sweep_reversal.py`
treats every level independently and targets a fixed point value near the
sweep itself. This candidate requires a multi-level run (a real
directional push, not a single-bar poke) as the trigger, and targets a
specific, named opposing pool (e.g. the Asian low, if the run took out the
PD high and the Asian high) as the target — a structurally different,
context-dependent target rather than a fixed distance.

**Market regime needed:** a session with real directional conviction
(London or the London/NY overlap, per this repo's own session-window
finding — not Asia).

**Entry rule (pseudocode):**
```
1. IF price takes out 2+ marked liquidity levels in the same direction within the session (a "run", not a single sweep)
2. AND the M5 candle following the second level taken shows a displacement reversal (per candidate #1's displacement definition)
3. THEN enter in the reversal direction, targeting the nearest UNTOUCHED opposing-side liquidity pool.
```

**Stop rule:** beyond the run's own final extreme.
**Target rule:** the specific named opposing liquidity pool (context-dependent, not fixed).
**Invalidation:** the displacement reversal fails to hold — price retakes the run's extreme.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `min_levels_in_run` | 2 | 2-3 | Distinguishes a real run from a single-level sweep |

**Confidence/confirmation layer:** how far (in ATR multiples) the run
extended beyond the second level (a longer run before reversing suggests
more exhaustion), RSI divergence across the run.

**Expected failure mode:** a run that's actually the start of a real
multi-session trend, not exhaustion — the more levels taken, the more this
looks like genuine momentum rather than a stop-hunt, and the mechanism has
no clean way to distinguish the two in advance.

**Evidence tier:** T3, and honestly the weakest-sourced of the two
liquidity-sweep variants on this list — no source directly describes this
exact "multi-level run" refinement; it's a differentiation reasoned from
first principles (why the single-level version failed) rather than
lifted from a specific published source. Flagged as the candidate most in
need of P3's own data to validate the underlying premise before trusting
it.

---

### 10. Equal Highs/Lows Sweep + RSI Divergence (hard-gated)

**Mechanism:** the one candidate on this list where an indicator is a
**required gate**, not just a confidence input — matching Rakesh's own
"don't want to completely skip indicators" instruction with a concrete,
different treatment from the other 9. Trades a sweep of equal highs/lows
(a liquidity pool by definition — multiple touches at nearly the same
price mark a cluster of resting stops) ONLY when RSI(14) shows a
divergence at the sweep (price makes a new extreme, RSI does not) — no
divergence, no trade, regardless of how clean the sweep looks.

**Market regime needed:** any — the divergence requirement itself is meant
to be the regime filter (divergences are rarer in strong trends, more
common at genuine exhaustion points).

**Entry rule (pseudocode):**
```
1. Identify equal highs/lows: 2+ swing points within 0.1% of each other (default; range 0.05-0.2%) in the last 50 M5 bars.
2. IF price sweeps that level
3. AND RSI(14) at the sweep bar is LESS extreme than RSI(14) at the prior equal-level touch (bearish divergence for a high-sweep, bullish for a low-sweep) — THIS IS A HARD REQUIREMENT, not optional
4. THEN enter in the reversal direction on the sweep bar's own close back inside the level.
```

**Stop rule:** beyond the sweep's wick extreme.
**Target rule:** the next equal-highs/lows cluster in the opposite direction.
**Invalidation:** no divergence present — the setup never triggers at all, not just a lower-confidence trigger.

**Parameter table:**
| Name | Default | Search range | Why |
|---|---|---|---|
| `equal_level_tolerance_pct` | 0.1% | 0.05-0.2% | — |
| `rsi_period` | 14 | 9-21 | Standard RSI convention |

**Confidence/confirmation layer:** since RSI divergence is already a hard
gate here, the *additional* informational layer is the divergence's
magnitude (a larger RSI gap between the two touches is a stronger signal)
and the loss-streak component.

**Expected failure mode:** RSI divergence is well known to persist through
multiple touches before a reversal actually happens ("divergence keeps
diverging") — a hard gate on it risks either too few signals (if strict)
or false confidence (if the divergence itself isn't reliable at this
timeframe).

**Evidence tier:** T3 for the combined rule (this specific "equal-highs
sweep + RSI-divergence gate" pairing isn't sourced from any single
external reference — it's my own synthesis of two separately-documented
ideas: equal-highs/lows as a liquidity concept from the ICT/SMC literature,
and RSI divergence as a classical, decades-old technical signal). Flagged
honestly as a synthesis, not a found-and-verified external strategy.
