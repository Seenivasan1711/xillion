import sys
sys.path.insert(0, ".")
from collections import Counter
import run_backtests as rb
from engine.backtest_engine import StrategyContext
from signals.indicators import IndicatorSignals
from signals.price_action import PriceActionSignals
from strategies.s11_video_liquidity_mtf_scalp import VideoLiquidityMtfScalpStrategy

pa = PriceActionSignals(); ind = IndicatorSignals()
strat = VideoLiquidityMtfScalpStrategy()
p = strat.p
all_bars = rb.load_all_bars()
print(f"bars={len(all_bars)}", flush=True)

c = Counter()
STEP = 5  # sample every 5th bar; caching makes this cheap enough
for i in range(200, len(all_bars), STEP):
    hist = all_bars[:i]
    c["checked"] += 1
    h1_bars = hist[-p.h1_bars_window:]
    if len(h1_bars) < 100:
        c["h1_too_few_bars"] += 1; continue
    h1_res = strat._cached_resample(h1_bars, 60, "h1")
    if len(h1_res) < 30:
        c["h1_too_few_resampled"] += 1; continue
    h1_atr = ind.atr(h1_res, period=14)
    if h1_atr <= 0:
        c["h1_atr_zero"] += 1; continue
    h1_bos = pa.break_of_structure(h1_res, atr_value=h1_atr, swing_lookback=p.swing_lookback,
                                   decisive_atr_mult=p.decisive_atr_mult)
    if not h1_bos.fired:
        c["GATE1_h1_bos_not_fired"] += 1; continue
    c["passed_h1_bos"] += 1
    bias = h1_bos.direction

    m15_res = strat._cached_resample(hist[-p.m15_bars_window:], 15, "m15")
    if len(m15_res) < 30:
        c["m15_too_few"] += 1; continue
    m15_atr = ind.atr(m15_res, period=14)
    if m15_atr <= 0:
        c["m15_atr_zero"] += 1; continue
    m15_bos = pa.break_of_structure(m15_res, atr_value=m15_atr, swing_lookback=p.swing_lookback,
                                    decisive_atr_mult=p.decisive_atr_mult)
    if not m15_bos.fired:
        c["GATE2_m15_bos_not_fired"] += 1; continue
    if m15_bos.direction != bias:
        c["GATE3_direction_mismatch"] += 1; continue
    c["passed_alignment"] += 1

    poi = pa.order_block_zone(m15_res, m15_bos)
    if not poi.fired:
        c["GATE4_poi_not_mitigated"] += 1; continue
    c["passed_poi"] += 1

    swings = pa._find_swing_points(hist[-p.swing_search_bars:], p.swing_lookback)
    want_high = (bias.value == "down")
    cands = [s for s in swings if s.is_high == want_high]
    if not cands:
        c["GATE5_no_swing_candidate"] += 1; continue
    c["passed_swing_found_would_set_pending"] += 1

for k, v in c.most_common():
    print(f"{k:45s} {v}")
