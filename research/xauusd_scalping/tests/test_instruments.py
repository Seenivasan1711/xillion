"""Instrument specs (engine/instruments.py) -- forex support, 2026-09-24.

Every expected number here is hand-derived from the broker contract spec,
not read back from the code under test."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from research.xauusd_scalping.engine.backtest_engine import (
    BacktestEngine,
    Bar,
    RiskLimits,
    Side,
    Signal,
    SizingConfig,
)
from research.xauusd_scalping.engine.cost_model import CostModel, Session, VolBucket
from research.xauusd_scalping.engine.instruments import (
    INSTRUMENTS,
    equivalent_lots,
    get_instrument,
    measure_price_scale,
    scale_strategy_params,
)


def test_contract_economics_per_symbol():
    # XAUUSD: 1 lot = 100oz -> $100 per $1.00 move.
    assert INSTRUMENTS["XAUUSD"].usd_per_price_unit_per_lot == pytest.approx(100.0)
    # EURUSD: 1 lot = 100,000 EUR, USD-quoted -> $100,000 per 1.00000 move,
    # i.e. $10 per pip (0.0001) per lot -- the standard FX figure.
    eur = INSTRUMENTS["EURUSD"]
    assert eur.usd_per_price_unit_per_lot == pytest.approx(100_000.0)
    assert eur.usd_per_price_unit_per_lot * 0.0001 == pytest.approx(10.0)


def test_engine_charges_eurusd_costs_in_eurusd_points():
    """A EURUSD long, London/MEDIUM: measured spread 3pts -> half = 1.5pts =
    0.000015 of price per side (NOT 1.5, NOT 0.015). Zero slippage and
    commission to isolate the spread. 1.0 lot, +0.00100 (10 pip) move:
    net = (0.00100 - 0.00003) x 100,000 = $97.00."""
    eur = get_instrument("EURUSD", price_scale=0.0002)
    cost = CostModel(
        commission_per_lot_per_side=0.0, entry_slippage_pts=0.0, exit_slippage_pts=0.0,
        spread_table=eur.spread_table, point_size=eur.point_size,
    )
    ts0 = datetime(2026, 1, 5, 9, tzinfo=UTC)  # London
    px = [1.10000, 1.10050, 1.10100, 1.10150]
    bars = [Bar(ts=ts0 + timedelta(minutes=i), open=p, high=p, low=p, close=p, volume=0) for i, p in enumerate(px)]

    class Once:
        fired = False

        def on_bar(self, bar, ctx):
            if self.fired:
                return None
            self.fired = True
            return Signal(side=Side.LONG, stop_price=1.09000, target_price=1.10100)

    engine = BacktestEngine(
        cost_model=cost, sizing=SizingConfig(fixed_lots=1.0, point_value_usd=eur.point_value_usd),
        risk=RiskLimits(min_sl_pts=None, min_target_pts=None),
    )
    t = engine.run(bars, Once()).trades[0]
    assert eur.spread_table[(Session.LONDON, VolBucket.MEDIUM)] == 3.0
    assert t.entry_price == pytest.approx(1.100015)
    assert t.exit_price == pytest.approx(1.101 - 0.000015)
    assert t.pnl_usd == pytest.approx(97.0)


@dataclass
class _FakeParams:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    swing_lookback: int = 3  # not a price distance -- must NOT be scaled
    decisive_atr_mult: float = 0.3  # scale-free -- must NOT be scaled


def test_scale_strategy_params_scales_only_price_distances():
    eur = get_instrument("EURUSD", price_scale=0.0002)
    p = scale_strategy_params(_FakeParams(), eur)
    assert p.min_sl_pts == pytest.approx(0.0006)  # $3 on gold -> 6 pips
    assert p.sl_buffer_pts == pytest.approx(0.0001)
    assert p.swing_lookback == 3
    assert p.decisive_atr_mult == 0.3


def test_unmeasured_scale_is_refused_not_guessed():
    with pytest.raises(ValueError, match="price_scale"):
        scale_strategy_params(_FakeParams(), INSTRUMENTS["EURUSD"])
    with pytest.raises(ValueError):
        equivalent_lots(INSTRUMENTS["EURUSD"])


def test_equivalent_lots_matches_gold_risk_per_stop():
    """Gold: 0.08 lot x $3 stop x $100/lot = $24 risk. EURUSD at scale
    0.0002: stop = 0.0006, so lots = 24 / (0.0006 x 100,000) = 0.4."""
    eur = get_instrument("EURUSD", price_scale=0.0002)
    lots = equivalent_lots(eur)
    assert lots == pytest.approx(0.4)
    assert lots * 3.0 * 0.0002 * eur.usd_per_price_unit_per_lot == pytest.approx(24.0)


def test_measure_price_scale_is_ratio_of_median_daily_ranges():
    def day_bars(start, n_days, rng):
        out = []
        for d in range(n_days):
            ts = start + timedelta(days=d)
            out.append(Bar(ts=ts, open=0, high=rng, low=0, close=0, volume=0))
        return out

    start = datetime(2026, 1, 1, tzinfo=UTC)
    gold = day_bars(start, 30, 40.0)  # $40/day
    eur = day_bars(start, 30, 0.0070)  # 70 pips/day
    assert measure_price_scale(eur, gold) == pytest.approx(0.0070 / 40.0)
    with pytest.raises(ValueError, match="overlapping"):
        measure_price_scale(day_bars(start, 5, 0.007), gold)
