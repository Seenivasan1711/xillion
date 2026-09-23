"""
C1 diagnostic (per the pasted external review, 2026-09-23): re-run all 10
strategies' EXACT existing signal/stop/target logic with the cost model
zeroed out, to separate "no signal" from "signal exists, costs kill it."
Same trades as the real-cost run would generate given the same bars --
only the fill/PnL math changes. Not a redesign of the strategies.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from engine.backtest_engine import RiskLimits, SizingConfig  # noqa: E402
from engine.cost_model import CostModel  # noqa: E402
import run_backtests as rb  # noqa: E402


def make_zero_cost_engine():
    from engine.backtest_engine import BacktestEngine
    return BacktestEngine(
        cost_model=CostModel.zero(),
        sizing=SizingConfig(mode="fixed_lot", fixed_lots=0.08),
        risk=RiskLimits(max_trades_per_session=4, daily_loss_cap_usd=50.0, consecutive_loss_halt=2),
    )


rb.make_engine = make_zero_cost_engine


def main():
    all_bars = rb.load_all_bars()
    print(f"Total bars: {len(all_bars)} ({all_bars[0].ts} -> {all_bars[-1].ts})")
    print("ZERO-COST RUN (C1 diagnostic)")
    print()

    results = {}
    for name, cls in rb.STRATEGIES:
        strat_all = cls()
        eng_all = make_zero_cost_engine()
        res_all = eng_all.run(all_bars, strat_all)
        m_all = rb.compute_metrics(res_all.trades)
        results[name] = m_all
        print(f"{name}: n={m_all.get('n', 0)} win%={m_all.get('win_rate', 0):.1f} "
              f"PF={m_all.get('profit_factor', 0):.2f} avgR={m_all.get('avg_r', 0):.3f} "
              f"PnL(zero-cost)=${m_all.get('total_pnl', 0):.2f} maxDD%={m_all.get('max_dd_pct', 0):.1f}")

    import json
    with open(Path(__file__).parent / "_zero_cost_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nWritten to _zero_cost_results.json")


if __name__ == "__main__":
    main()
