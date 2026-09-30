"""Prop-account limits (2026-09-30): exact limit maths, the EET server-day
boundary, and "warn once per level change"."""

from datetime import UTC, datetime

import pytest

from xillion.engine.prop_account import ClosedTrade, PropConfig, compute_status, crossed, server_day

CFG = PropConfig(account="1", phase="phase1", start_balance=5000, start_date="2026-09-01")
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)  # 15:00 EEST


def _t(iso: str, pnl: float) -> ClosedTrade:
    return ClosedTrade(close_time=datetime.fromisoformat(iso), net_pnl=pnl)


def _lim(st, prefix):
    return next(lim for lim in st.limits if lim.name.startswith(prefix))


def test_server_day_rolls_at_eet_midnight():
    assert server_day(datetime(2026, 9, 28, 20, 59, tzinfo=UTC)) == "2026-09-28"  # 23:59 EEST
    assert server_day(datetime(2026, 9, 28, 21, 0, tzinfo=UTC)) == "2026-09-29"  # 00:00 EEST
    assert (
        server_day(datetime(2026, 1, 15, 22, 0, tzinfo=UTC)) == "2026-01-16"
    )  # 00:00 EET (winter)


def test_limits_from_closed_trades():
    trades = [
        _t("2026-09-10T10:00:00+00:00", 300.0),  # earlier day: +300
        _t("2026-09-29T08:00:00+00:00", -30.0),  # today
        _t("2026-09-29T09:00:00+00:00", -12.0),  # today
        _t("2026-08-15T09:00:00+00:00", -999.0),  # before the phase started: ignored
    ]
    st = compute_status(CFG, trades, NOW)
    assert st.today_pnl == -42.0 and st.total_pnl == 258.0 and st.balance == 5258.0
    mine, daily, maxl = _lim(st, "Your"), _lim(st, "Daily"), _lim(st, "Max")
    assert (mine.limit_usd, mine.used_usd, mine.level) == (50.0, 42.0, "warn")  # 84% >= 80%
    # 4% of the day's OPENING balance (5000 + 300)
    assert daily.limit_usd == pytest.approx(212.0) and daily.level == "ok"
    assert maxl.limit_usd == 600.0 and maxl.used_usd == 0.0
    assert st.target_usd == 500.0 and st.target_progress_pct == pytest.approx(51.6)
    assert st.trading_days == 2 and st.profitable_days == 1  # +300 >= 0.5% of 5000; -42 isn't
    assert st.level == "warn"


def test_breach_and_warn_once_per_level_change():
    before = compute_status(CFG, [_t("2026-09-29T08:00:00+00:00", -30.0)], NOW)
    mid = compute_status(CFG, [_t("2026-09-29T08:00:00+00:00", -45.0)], NOW)
    after = compute_status(CFG, [_t("2026-09-29T08:00:00+00:00", -55.0)], NOW)
    assert [lim.name for lim in crossed(before, mid)] == ["Your daily stop"]  # ok -> warn
    assert crossed(mid, mid) == []  # same level again: no repeat warning
    worse = crossed(mid, after)
    assert [(lim.name, lim.level) for lim in worse] == [("Your daily stop", "breach")]


def test_master_phase_has_no_target_and_drawdown_uses_start_balance():
    cfg = PropConfig(account="1", phase="master", start_balance=5000, start_date="2026-09-01")
    st = compute_status(cfg, [_t("2026-09-10T10:00:00+00:00", -500.0)], NOW)
    assert st.target_usd is None
    maxl = _lim(st, "Max")
    assert maxl.used_usd == 500.0 and maxl.level == "warn"  # 83% of the 600 static floor
