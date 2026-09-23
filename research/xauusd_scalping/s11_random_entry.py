import sys, json, random, statistics
sys.path.insert(0, ".")
import run_backtests as rb
from engine.backtest_engine import Side
import random_entry_benchmark as reb

bars = rb.load_all_bars()
session_index = reb.build_session_index(bars)
trades = json.load(open("_s11_trades_real.json"))
n = len(trades)
real_pnl = sum(t["pnl"] for t in trades)
sessions = [t["session"] for t in trades]
rr_pairs = [(abs(t["entry"] - t["stop"]), abs(t["target"] - t["entry"])) for t in trades]
print(f"S11 real: n={n} pnl=${real_pnl:.2f}", flush=True)

N_RUNS = 500
rng = random.Random(20260924)
run_pnls, timeouts = [], 0
for run in range(N_RUNS):
    total = 0.0
    for _ in range(n):
        sess = rng.choice(sessions)
        pool = session_index.get(sess, [])
        if not pool:
            continue
        entry_idx = rng.choice(pool)
        if entry_idx >= len(bars) - 10:
            entry_idx = rng.choice(pool)
        side = Side.LONG if rng.random() < 0.5 else Side.SHORT
        stop_pts, target_pts = rng.choice(rr_pairs)
        t = reb.resolve_one_trade(rb.make_engine(), bars, entry_idx, side, stop_pts, target_pts)
        if t is None:
            timeouts += 1
            continue
        total += t.pnl_usd
    run_pnls.append(total)
    if (run + 1) % 100 == 0:
        print(f"  {run+1}/{N_RUNS} runs done", flush=True)

run_pnls.sort()
p5, p50, p95 = run_pnls[int(N_RUNS*0.05)], run_pnls[int(N_RUNS*0.50)], run_pnls[int(N_RUNS*0.95)]
if real_pnl < p5:
    verdict = "BELOW random p5 -- worse than random noise"
elif real_pnl > p95:
    verdict = "ABOVE random p95 -- distinguishable from random (positive signal)"
else:
    verdict = "INSIDE random p5-p95 band -- statistically indistinguishable from random noise"
print(f"S11: n={n} real=${real_pnl:.2f} random[p5=${p5:.2f} p50=${p50:.2f} p95=${p95:.2f} "
      f"mean=${statistics.mean(run_pnls):.2f}] timeouts={timeouts}/{n*N_RUNS} -> {verdict}", flush=True)
