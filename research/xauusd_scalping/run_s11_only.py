import sys
sys.path.insert(0, ".")
import run_backtests as rb
from engine.backtest_engine import BacktestEngine, RiskLimits, SizingConfig
from engine.cost_model import CostModel
from strategies.s11_video_liquidity_mtf_scalp import VideoLiquidityMtfScalpStrategy

all_bars = rb.load_all_bars()
print(f"Total bars: {len(all_bars)} ({all_bars[0].ts} -> {all_bars[-1].ts})", flush=True)

def make_engine(zero_cost=False):
    return BacktestEngine(
        cost_model=CostModel.zero() if zero_cost else CostModel(),
        sizing=SizingConfig(mode="fixed_lot", fixed_lots=0.08),
        risk=RiskLimits(max_trades_per_session=4, daily_loss_cap_usd=50.0, consecutive_loss_halt=2),
    )

for label, zero in (("REAL COST", False), ("ZERO COST", True)):
    strat = VideoLiquidityMtfScalpStrategy()
    result = make_engine(zero_cost=zero).run(all_bars, strat)
    m = rb.compute_metrics(result.trades)
    print(f"S11 [{label}]: {m}", flush=True)
    if result.trades:
        import json
        with open(f"_s11_trades_{'zero' if zero else 'real'}.json", "w") as f:
            json.dump([{
                "entry_ts": str(t.entry_ts), "side": t.side.value, "session": t.session,
                "entry": t.entry_price, "stop": t.stop_price, "target": t.target_price,
                "exit": t.exit_price, "reason": t.exit_reason, "pnl": t.pnl_usd, "r": t.r_multiple,
            } for t in result.trades], f, indent=2)
