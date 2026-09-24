"""
Per-symbol instrument specs, so the harness can run forex pairs as well as
XAUUSD (Rakesh's direction 2026-09-24: gold first, forex next).

Everything that used to be a hidden XAUUSD constant lives here: the
Dukascopy price divisor, the MT5 point size, USD per point per lot, the
spread table, and `price_scale` -- the factor that converts the strategies'
gold-dollar distance params (`min_sl_pts=3.0` means a $3.00 stop on gold)
into the same *relative* distance on another symbol.

`price_scale` is MEASURED, never guessed: median daily high-low range of the
symbol / median daily range of XAUUSD over the same period, via
`measure_price_scale()`. A symbol whose scale hasn't been measured yet has
`price_scale=None` and `scale_strategy_params` refuses to run it -- a guessed
scale would silently decide every stop distance.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path

from .cost_model import _SPREAD_TABLE as _XAUUSD_SPREAD_TABLE
from .cost_model import Session, VolBucket


@dataclass(frozen=True)
class Instrument:
    symbol: str
    dukascopy_divisor: int  # raw bi5 integer price / divisor = price
    point_size: float  # MT5 point, in price units
    point_value_usd: float  # USD P&L per point per 1.0 lot
    spread_table: dict[tuple[Session, VolBucket], float]  # in POINTS
    spread_is_measured: bool  # False = stated assumption, needs a real MT5 reading
    commission_per_lot_per_side: float
    price_scale: float | None  # see module docstring; None = not yet measured

    @property
    def usd_per_price_unit_per_lot(self) -> float:
        """USD P&L for a 1.0 price move on 1.0 lot (XAUUSD: $100, EURUSD: $100,000)."""
        return self.point_value_usd / self.point_size

    @property
    def data_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data" / self.symbol.lower()


def _profile(rows: dict[Session, tuple[float, float, float]]) -> dict[tuple[Session, VolBucket], float]:
    """(p25, median, p75) per session -> LOW=p25, MEDIUM=median,
    HIGH=max(p75, 1.5x median); dead zone HIGH=2.5x median, because rollover
    spikes last minutes and per-hour medians hide them."""
    out = {}
    for sess, (p25, med, p75) in rows.items():
        high = med * 2.5 if sess == Session.DEAD_ZONE else max(p75, med * 1.5)
        out[(sess, VolBucket.LOW)] = p25
        out[(sess, VolBucket.MEDIUM)] = med
        out[(sess, VolBucket.HIGH)] = high
    return out


# FX spread tables, in points (1pt = 0.00001, 10pt = 1 pip). MEASURED
# 2026-09-24 by measure_fx_spread_profile.py: per-hour median bid/ask spread
# from Dukascopy ticks, 3 mid-week days (2026-06-09, 06-17, 07-08), rows are
# (p25, median, p75) of those per-hour medians. Dukascopy is used as a
# conservative PROXY for the broker: Rakesh's FundingPips MT5 reading the
# same day (16:56 server time, London/NY overlap) was EURUSD 1pt / GBPUSD 0pt
# -- below Dukascopy's 3 / 6. The broker is a raw-spread account, so its real
# cost is mostly commission (see Instrument.commission_per_lot_per_side).
_EURUSD_SPREAD_TABLE = _profile({
    Session.LONDON_NY_OVERLAP: (3.0, 3.0, 3.0),
    Session.LONDON: (3.0, 3.0, 3.0),
    Session.NY: (3.0, 3.0, 5.2),
    Session.ASIA: (3.0, 3.0, 3.0),
    Session.DEAD_ZONE: (4.0, 4.0, 4.0),  # only 3 sampled hours
})
_GBPUSD_SPREAD_TABLE = _profile({
    Session.LONDON_NY_OVERLAP: (6.0, 6.0, 6.0),
    Session.LONDON: (6.0, 6.0, 6.0),
    Session.NY: (6.0, 7.0, 12.0),
    Session.ASIA: (6.0, 7.0, 8.0),
    Session.DEAD_ZONE: (8.0, 8.0, 8.0),  # only 3 sampled hours
})


INSTRUMENTS: dict[str, Instrument] = {
    "XAUUSD": Instrument(
        symbol="XAUUSD",
        dukascopy_divisor=1000,  # verified empirically 2026-09-22, see download_dukascopy.py
        point_size=0.01,
        point_value_usd=1.0,  # 1 lot = 100oz x $0.01
        spread_table=_XAUUSD_SPREAD_TABLE,
        spread_is_measured=True,  # NY reading 31pts vs table 30 (2026-09-24)
        commission_per_lot_per_side=2.50,  # measured, see CostModel
        price_scale=1.0,  # the reference instrument
    ),
    "EURUSD": Instrument(
        symbol="EURUSD",
        dukascopy_divisor=100_000,  # verified 2026-09-24: 2026-09-15 10h UTC parsed to 1.15373
        point_size=0.00001,
        point_value_usd=1.0,  # 1 lot = 100,000 EUR x 0.00001 = $1 (USD-quoted)
        spread_table=_EURUSD_SPREAD_TABLE,
        spread_is_measured=True,  # Dukascopy-measured profile; broker reading is at/below it
        commission_per_lot_per_side=2.50,  # ASSUMED same as XAUUSD until the MT5 spec is read
        price_scale=None,
    ),
    "GBPUSD": Instrument(
        symbol="GBPUSD",
        dukascopy_divisor=100_000,
        point_size=0.00001,
        point_value_usd=1.0,
        spread_table=_GBPUSD_SPREAD_TABLE,
        spread_is_measured=True,  # Dukascopy-measured profile; broker reading is at/below it
        commission_per_lot_per_side=2.50,
        price_scale=None,
    ),
}


def get_instrument(symbol: str, price_scale: float | None = None) -> Instrument:
    inst = INSTRUMENTS[symbol.upper()]
    return replace(inst, price_scale=price_scale) if price_scale is not None else inst


# Strategy param fields that are gold-DOLLAR distances (see e.g.
# strategies/s01_liquidity_sweep_fvg.py Params). Listed explicitly rather
# than matched by suffix, so a new field is never scaled by accident.
PRICE_DISTANCE_FIELDS = ("min_sl_pts", "sl_buffer_pts", "bin_pts", "fallback_target_pts")


def scale_strategy_params(params, instrument: Instrument):
    """Returns a copy of a strategy's Params with every gold-dollar distance
    field multiplied by the instrument's measured price_scale."""
    if instrument.price_scale is None:
        raise ValueError(
            f"{instrument.symbol} has no measured price_scale -- run "
            "measure_price_scale() on real data first; never guess it."
        )
    names = {f.name for f in fields(params)}
    changes = {
        name: getattr(params, name) * instrument.price_scale
        for name in PRICE_DISTANCE_FIELDS
        if name in names
    }
    return replace(params, **changes)


def equivalent_lots(instrument: Instrument, xauusd_lots: float = 0.08) -> float:
    """Lot size giving the same USD risk per stop as `xauusd_lots` on gold,
    once stops are scaled by price_scale. Keeps the $50 daily cap and the
    random benchmark comparable across symbols."""
    if instrument.price_scale is None:
        raise ValueError(f"{instrument.symbol} has no measured price_scale")
    gold = INSTRUMENTS["XAUUSD"]
    return (
        xauusd_lots
        * gold.usd_per_price_unit_per_lot
        / (instrument.usd_per_price_unit_per_lot * instrument.price_scale)
    )


def measure_price_scale(symbol_bars, xauusd_bars) -> float:
    """Median daily (UTC) high-low range of `symbol_bars` / that of
    `xauusd_bars`, over the dates both cover. Bars: objects with ts/high/low."""
    from statistics import median

    def daily_ranges(bars) -> dict:
        hi: dict = {}
        lo: dict = {}
        for b in bars:
            d = b.ts.date()
            hi[d] = max(hi.get(d, b.high), b.high)
            lo[d] = min(lo.get(d, b.low), b.low)
        return {d: hi[d] - lo[d] for d in hi}

    a, g = daily_ranges(symbol_bars), daily_ranges(xauusd_bars)
    common = sorted(set(a) & set(g))
    if len(common) < 20:
        raise ValueError(f"only {len(common)} overlapping days -- need >= 20 for a stable scale")
    return median(a[d] for d in common) / median(g[d] for d in common)
