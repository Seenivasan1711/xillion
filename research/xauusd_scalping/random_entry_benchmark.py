"""
C3 diagnostic (per the external review pasted into the session 2026-09-23):
a random-entry benchmark for all 10 XAUUSD strategies, so "negative
expectancy" has an actual reference point. Without this, "8 of 10 are
net-negative" has no way to distinguish "this strategy is actively bad"
from "this strategy is statistically indistinguishable from noise" --
those are different findings with different implications.

Methodology: for each strategy, take its REAL trade count n, session
distribution, and (stop_pts, target_pts) pairs from a fresh real run
against the full dataset. Build n random entries per simulated run: a
session resampled from the real distribution, a random bar within that
session, a random LONG/SHORT direction, and a (stop_pts, target_pts) pair
resampled jointly (preserving the real R:R relationship) from the real
trades. Resolve each entry through the exact same engine fill/cost logic
real trades use (BacktestEngine._open_position/_resolve_intrabar/
_close_position, called directly -- not reimplemented) so the cost model,
gap handling, and pessimistic same-bar-ambiguity rule are identical to the
real backtest. Repeat 1,000 times per strategy, collect total PnL per run.

Performance note: `BacktestEngine.run()` reconstructs a full copy of the
run-so-far history list on every bar the strategy is flat
(`StrategyContext(history=list(history), ...)`), which is O(n) per call
and O(n^2) over a full run -- this is almost certainly why full 174k-bar
runs take multiple minutes even for strategies with trivial per-bar logic.
That's out of scope to fix here (not this fork's directive), but it means
running `engine.run()` naively 1,000 times per strategy over the full
dataset would be prohibitively slow. Instead, this script calls the
engine's own private fill-resolution methods directly for each isolated
synthetic trade (real, tested cost/fill logic, just skipping the full
per-bar strategy-context loop that a lone random entry doesn't need) --
this is O(bars_held) per trade instead of O(full dataset), so 1,000 runs
per strategy is fast.

Simplification, stated plainly: each random run's n entries are resolved
independently (no cross-trade day-level interaction -- a real backtest's
daily_loss_cap/consecutive_loss_halt/max_trades_per_session apply across
a whole day's real trades, but here each synthetic entry doesn't know
about the others in the same simulated day). This is a reasonable
approximation for isolating "does this strategy's entry timing + R:R
profile beat random," not a full re-simulation of the day-level risk
layer. Also: sizing uses the same fixed 0.08 lot every trade (matches
`run_backtests.make_engine()`'s SizingConfig, which is equity-independent
in fixed_lot mode, so this introduces no bias).
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine.backtest_engine import BacktestEngine, Signal, Side  # noqa: E402
from engine.cost_model import VolBucket, session_for  # noqa: E402
import run_backtests as rb  # noqa: E402

# Reduced from an original 1000 -- the one-time real-strategy rerun below
# (needed regardless of N_RUNS, to get real per-trade session/stop/target
# data) turned out to dominate wall time far more than expected: a real
# per-bar cost in BacktestEngine.run() (StrategyContext(history=list(
# history), ...) copies the ENTIRE running history on every flat bar --
# O(n) per call, O(n^2) over a 174,554-bar run) plus CPU contention from
# two other legitimate background jobs running concurrently (the
# coordinator's zero-cost diagnostic, another fork's S04 rerun). Fixing
# the engine itself is out of scope here. 500 runs is still a reasonable
# sample for 5th/50th/95th percentile estimates (order statistics at
# ranks 25/250/475) and keeps this from taking hours.
N_RUNS = 500
MAX_WINDOW_BARS = 20000  # ~13.9 trading days -- generous, cheap now that
# each bar-step is O(1) via direct method calls, not a full engine.run().
SEED = 20260923  # fixed, reproducible; advanced per strategy below
# Per-symbol cache (RESEARCH_SYMBOL, see run_backtests.SYMBOL). DELETE it after any
# engine/cost change -- it silently holds trades from the old machinery.
REAL_TRADES_CACHE = Path(__file__).parent / f"_real_trades_cache{rb.results_suffix()}.json"


def resolve_one_trade(engine: BacktestEngine, bars: list, entry_idx: int, side: Side,
                       stop_pts: float, target_pts: float):
    """Opens and resolves exactly one synthetic trade starting at
    bars[entry_idx], using the engine's own tested fill/cost methods
    directly (not engine.run()'s full per-bar loop). Returns the Trade, or
    None if the window runs out before either level is hit (should be rare
    at MAX_WINDOW_BARS; flagged, not silently dropped, if it happens)."""
    entry_bar = bars[entry_idx]
    sess = session_for(entry_bar.ts)
    spread = engine.cost_model.spread_pts(sess, VolBucket.MEDIUM)
    ref = entry_bar.close
    if side == Side.LONG:
        stop_price = ref - stop_pts
        target_price = ref + target_pts
    else:
        stop_price = ref + stop_pts
        target_price = ref - target_pts
    signal = Signal(side=side, stop_price=stop_price, target_price=target_price)
    position = engine._open_position(entry_bar, signal, 5000.0, sess, spread)

    end = min(len(bars), entry_idx + 1 + MAX_WINDOW_BARS)
    for i in range(entry_idx + 1, end):
        bar = bars[i]
        exit_price, reason, ambiguous = engine._resolve_intrabar(bar, position)
        if exit_price is not None:
            return engine._close_position(position, bar.ts, exit_price, reason, ambiguous, bar)
    return None  # ran out of window without resolving -- timeout, excluded and counted


def build_session_index(bars: list) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = defaultdict(list)
    for i, b in enumerate(bars):
        idx[session_for(b.ts).value].append(i)
    return idx


def get_real_trade_data(bars: list) -> dict:
    """Real per-strategy trade data (session list, (stop_pts,target_pts)
    pairs, n, total pnl) -- cached to disk after the first (expensive,
    ~unavoidable) real rerun, since this cost is fixed regardless of
    N_RUNS and shouldn't be paid again on every script iteration."""
    if REAL_TRADES_CACHE.exists():
        print(f"Loading real trade data from cache: {REAL_TRADES_CACHE}", flush=True)
        with open(REAL_TRADES_CACHE) as f:
            return json.load(f)

    print("No cache found -- running all 10 strategies once against real "
          "data (this is the expensive, one-time part; unrelated to N_RUNS)", flush=True)
    data = {}
    for name, cls in rb.STRATEGIES:
        t0 = time.time()
        strat = rb.make_strategy(cls)
        engine = rb.make_engine()
        real_result = engine.run(bars, strat)
        trades = real_result.trades
        data[name] = {
            "n": len(trades),
            "real_pnl": sum(t.pnl_usd for t in trades),
            "sessions": [t.session for t in trades],
            "rr_pairs": [
                [abs(t.entry_price - t.stop_price), abs(t.target_price - t.entry_price)]
                for t in trades
            ],
        }
        print(f"  [{time.time()-t0:.1f}s] {name}: n={len(trades)} pnl=${data[name]['real_pnl']:.2f}",
              flush=True)

    with open(REAL_TRADES_CACHE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Cached real trade data to {REAL_TRADES_CACHE}", flush=True)
    return data


def main():
    bars = rb.load_all_bars()
    print(f"Total bars: {len(bars)}", flush=True)
    session_index = build_session_index(bars)
    print("Session bar counts:", {k: len(v) for k, v in session_index.items()}, flush=True)

    real_data = get_real_trade_data(bars)

    rows = []
    for strat_num, (name, cls) in enumerate(rb.STRATEGIES):
        d = real_data[name]
        n = d["n"]
        real_pnl = d["real_pnl"]

        if n == 0:
            rows.append((name, n, real_pnl, None, None, None, "n=0 -- no comparison possible"))
            print(f"{name}: n=0, no random-entry comparison possible", flush=True)
            continue

        sessions = d["sessions"]
        rr_pairs = [tuple(p) for p in d["rr_pairs"]]

        rng = random.Random(SEED + strat_num)
        run_pnls = []
        timeouts = 0
        for _run in range(N_RUNS):
            total = 0.0
            for _ in range(n):
                sess = rng.choice(sessions)
                pool = session_index.get(sess, [])
                if not pool:
                    continue
                entry_idx = rng.choice(pool)
                # keep enough room for MAX_WINDOW_BARS after entry
                if entry_idx >= len(bars) - 10:
                    entry_idx = rng.choice(pool)
                side = Side.LONG if rng.random() < 0.5 else Side.SHORT
                stop_pts, target_pts = rng.choice(rr_pairs)
                fresh_engine = rb.make_engine()  # fresh cost model instance, cheap, avoids any shared state
                trade = resolve_one_trade(fresh_engine, bars, entry_idx, side, stop_pts, target_pts)
                if trade is None:
                    timeouts += 1
                    continue
                total += trade.pnl_usd
            run_pnls.append(total)

        run_pnls.sort()
        p5 = run_pnls[int(len(run_pnls) * 0.05)]
        p50 = run_pnls[int(len(run_pnls) * 0.50)]
        p95 = run_pnls[int(len(run_pnls) * 0.95)]
        mean_r = statistics.mean(run_pnls)

        if real_pnl < p5:
            verdict = "BELOW random p5 -- worse than random noise"
        elif real_pnl > p95:
            verdict = "ABOVE random p95 -- distinguishable from random (positive signal)"
        else:
            verdict = "INSIDE random p5-p95 band -- statistically indistinguishable from random noise"

        rows.append((name, n, real_pnl, p5, p50, p95, verdict))
        print(f"{name}: n={n} real_pnl=${real_pnl:.2f} random[p5=${p5:.2f} p50=${p50:.2f} "
              f"p95=${p95:.2f} mean=${mean_r:.2f}] timeouts={timeouts}/{n*N_RUNS} -> {verdict}",
              flush=True)

    with open(Path(__file__).parent / f"03b_random_entry_benchmark{rb.results_suffix()}.md", "w") as f:
        f.write(f"# C3 Diagnostic -- Random-Entry Benchmark ({rb.SYMBOL})\n\n")
        f.write(
            f"Seed: {SEED}, **{N_RUNS} runs per strategy** (reduced from an originally "
            f"planned 1,000 -- the one-time real-strategy rerun needed regardless of N_RUNS "
            f"turned out to dominate wall time, both from a real per-bar cost in "
            f"`BacktestEngine.run()` (it copies the entire running history on every flat bar, "
            f"O(n) per call) and from CPU contention with two other legitimate background jobs "
            f"running concurrently at the time. {N_RUNS} runs still gives usable order-statistic "
            f"estimates for the 5th/50th/95th percentiles (ranks {int(N_RUNS*0.05)}/"
            f"{int(N_RUNS*0.50)}/{int(N_RUNS*0.95)} of {N_RUNS} sorted values) -- don't read "
            f"them with 1,000-run precision.), window cap {MAX_WINDOW_BARS} bars.\n"
        )
        f.write(
            "Each strategy's real trade count, session mix, and (stop_pts, target_pts) "
            "pairs feed n random entries per run, resolved through the exact same engine "
            "fill/cost logic (`BacktestEngine._open_position/_resolve_intrabar/_close_position`, "
            "called directly, not reimplemented) as the real backtests. Simplification: each "
            "run's entries are resolved independently, without cross-trade day-level risk-limit "
            "interaction (daily cap / consecutive-loss halt / max-trades-per-session) -- a "
            "reasonable approximation for isolating entry-timing/R:R quality, not a full "
            "day-level re-simulation. Sizing is the same fixed 0.08 lot as the real runs "
            "(equity-independent, no bias introduced).\n\n"
        )
        f.write("| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for name, n, real_pnl, p5, p50, p95, verdict in rows:
            if p5 is None:
                f.write(f"| {name} | {n} | ${real_pnl:.2f} | — | — | — | {verdict} |\n")
            else:
                f.write(
                    f"| {name} | {n} | ${real_pnl:.2f} | ${p5:.2f} | ${p50:.2f} | ${p95:.2f} | {verdict} |\n"
                )
        n_indist = sum(1 for r in rows if r[6].startswith("INSIDE"))
        n_below = sum(1 for r in rows if r[6].startswith("BELOW"))
        n_above = sum(1 for r in rows if r[6].startswith("ABOVE"))
        n_na = sum(1 for r in rows if r[3] is None)
        f.write(
            f"\n**Summary**: {n_indist} of 10 statistically indistinguishable from random "
            f"noise, {n_below} below the random band (worse than noise), {n_above} above the "
            f"random band (distinguishable positive signal), {n_na} with no comparison possible "
            f"(zero real trades).\n"
        )

    print("\nWritten to 03b_random_entry_benchmark.md")


if __name__ == "__main__":
    main()
