"""Tests for market-hours and holiday gating."""

from datetime import datetime

from xillion.core.market_calendar import IST, is_market_open


def _ist(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_open_on_a_weekday_during_hours():
    assert is_market_open(_ist(2026, 7, 28, 10, 0)) is True  # Tuesday


def test_closed_on_saturday():
    assert is_market_open(_ist(2026, 8, 1, 10, 0)) is False


def test_closed_on_sunday():
    assert is_market_open(_ist(2026, 8, 2, 10, 0)) is False


def test_closed_on_listed_holiday_even_on_a_weekday():
    assert is_market_open(_ist(2026, 1, 26, 11, 0)) is False  # Republic Day, a Monday


def test_closed_before_market_open_boundary():
    assert is_market_open(_ist(2026, 7, 28, 9, 14)) is False


def test_open_exactly_at_market_open_boundary():
    assert is_market_open(_ist(2026, 7, 28, 9, 15)) is True


def test_open_exactly_at_market_close_boundary():
    assert is_market_open(_ist(2026, 7, 28, 15, 30)) is True


def test_closed_after_market_close_boundary():
    assert is_market_open(_ist(2026, 7, 28, 15, 31)) is False


def test_unknown_market_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown market calendar"):
        is_market_open(_ist(2026, 7, 28, 10, 0), market="FOREX_24_5")


def test_naive_datetime_assumed_utc():
    # 10:00 UTC = 15:30 IST on a Tuesday -- exactly at the close boundary.
    naive = datetime(2026, 7, 28, 10, 0)
    assert is_market_open(naive) is True
