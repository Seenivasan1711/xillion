"""Tests for options instrument resolution (strike/expiry/ATM logic)."""
from datetime import date
from decimal import Decimal

import pytest

from xillion.core.instruments import (
    ExpirySelectionError,
    InstrumentRow,
    StrikeResolutionError,
    nearest_strike,
    resolve_option,
    select_expiry,
)

TODAY = date(2026, 7, 28)  # a Tuesday


def _opt_row(
    token: int,
    exchange: str,
    tradingsymbol: str,
    name: str,
    expiry: date,
    strike: Decimal,
    option_type: str,
    lot_size: int = 25,
) -> InstrumentRow:
    return InstrumentRow(
        instrument_token=token,
        exchange=exchange,
        tradingsymbol=tradingsymbol,
        name=name,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        segment=f"{exchange}-OPT",
        lot_size=lot_size,
        tick_size=Decimal("0.05"),
    )


def _nifty_chain_for_expiry(expiry: date, strikes: list[int], token_start: int) -> list[InstrumentRow]:
    rows = []
    token = token_start
    for strike in strikes:
        for opt_type in ("CE", "PE"):
            rows.append(_opt_row(
                token, "NFO", f"NIFTY{expiry:%y%b%d}{strike}{opt_type}".upper(),
                "NIFTY", expiry, Decimal(strike), opt_type,
            ))
            token += 1
    return rows


# ── select_expiry: Nifty weekly ────────────────────────────────────────────────

def test_select_expiry_this_week_nifty():
    weekly_expiries = [date(2026, 7, 28), date(2026, 8, 4), date(2026, 8, 11)]
    rows = [r for e in weekly_expiries for r in _nifty_chain_for_expiry(e, [25000], 1000 + weekly_expiries.index(e) * 10)]
    assert select_expiry(rows, "NIFTY", "this_week", TODAY) == date(2026, 7, 28)


def test_select_expiry_next_week_nifty():
    weekly_expiries = [date(2026, 7, 28), date(2026, 8, 4), date(2026, 8, 11)]
    rows = [r for e in weekly_expiries for r in _nifty_chain_for_expiry(e, [25000], 1000 + weekly_expiries.index(e) * 10)]
    assert select_expiry(rows, "NIFTY", "next_week", TODAY) == date(2026, 8, 4)


# ── select_expiry: Sensex weekly, BFO exchange ─────────────────────────────────

def test_select_expiry_this_week_sensex_bfo():
    weekly_expiries = [date(2026, 7, 31), date(2026, 8, 7)]
    rows = []
    token = 2000
    for e in weekly_expiries:
        rows.append(_opt_row(token, "BFO", f"SENSEX{e:%y%b%d}80000CE".upper(), "SENSEX", e, Decimal(80000), "CE"))
        token += 1
    resolved = select_expiry(rows, "SENSEX", "this_week", TODAY)
    assert resolved == date(2026, 7, 31)


# ── select_expiry: BankNifty monthly-only ──────────────────────────────────────

def test_select_expiry_this_month_banknifty_monthly_only():
    monthly_expiries = [date(2026, 7, 30), date(2026, 8, 27)]
    rows = []
    token = 3000
    for e in monthly_expiries:
        rows.append(_opt_row(token, "NFO", f"BANKNIFTY{e:%y%b%d}52000CE".upper(), "BANKNIFTY", e, Decimal(52000), "CE"))
        token += 1
    assert select_expiry(rows, "BANKNIFTY", "this_month", TODAY) == date(2026, 7, 30)
    assert select_expiry(rows, "BANKNIFTY", "next_month", TODAY) == date(2026, 8, 27)


def test_select_expiry_this_week_raises_for_monthly_only_underlying():
    """The ambiguous case: 'this_week' requested for an underlying that only
    has monthly expiries far out -- must raise, not silently misresolve."""
    monthly_expiries = [date(2026, 8, 27)]
    rows = [_opt_row(4000, "NFO", "BANKNIFTY26AUG52000CE", "BANKNIFTY", monthly_expiries[0], Decimal(52000), "CE")]
    with pytest.raises(ExpirySelectionError, match="looks monthly-only"):
        select_expiry(rows, "BANKNIFTY", "this_week", TODAY)


def test_select_expiry_no_future_expiries_raises():
    rows = [_opt_row(5000, "NFO", "NIFTY_OLD", "NIFTY", date(2026, 1, 1), Decimal(25000), "CE")]
    with pytest.raises(ExpirySelectionError, match="no future expiries"):
        select_expiry(rows, "NIFTY", "this_week", TODAY)


def test_select_expiry_unknown_selector_raises():
    with pytest.raises(ValueError, match="unknown expiry selector"):
        select_expiry([], "NIFTY", "next_year", TODAY)


# ── nearest_strike ──────────────────────────────────────────────────────────────

def test_nearest_strike_atm_exact_match():
    strikes = [Decimal(s) for s in (24900, 24950, 25000, 25050, 25100)]
    assert nearest_strike(Decimal(25000), strikes, 0) == Decimal(25000)


def test_nearest_strike_atm_rounds_to_closest():
    strikes = [Decimal(s) for s in (24900, 24950, 25000, 25050, 25100)]
    assert nearest_strike(Decimal(25030), strikes, 0) == Decimal(25050)


def test_nearest_strike_otm_offset():
    strikes = [Decimal(s) for s in (24900, 24950, 25000, 25050, 25100)]
    # 2 strikes OTM for a call = 2 above ATM
    assert nearest_strike(Decimal(25000), strikes, 2) == Decimal(25100)


def test_nearest_strike_different_gap_sensex():
    # Sensex strike gaps are wider than Nifty's -- ladder is data-driven, not
    # a hardcoded interval.
    strikes = [Decimal(s) for s in (79800, 79900, 80000, 80100, 80200)]
    assert nearest_strike(Decimal(80060), strikes, 0) == Decimal(80100)


def test_nearest_strike_offset_out_of_range_raises():
    strikes = [Decimal(s) for s in (24900, 24950, 25000)]
    with pytest.raises(StrikeResolutionError, match="out of range"):
        nearest_strike(Decimal(25000), strikes, 5)


def test_nearest_strike_empty_raises():
    with pytest.raises(StrikeResolutionError, match="no strikes available"):
        nearest_strike(Decimal(25000), [], 0)


# ── resolve_option (end to end) ─────────────────────────────────────────────────

def test_resolve_option_atm_call_this_week():
    expiry = date(2026, 7, 28)
    rows = _nifty_chain_for_expiry(expiry, [24900, 24950, 25000, 25050, 25100], 6000)
    resolved = resolve_option(
        rows, "NIFTY", "this_week", strike_offset=0, option_type="CE",
        spot_price=Decimal(25010), as_of=TODAY,
    )
    assert resolved.strike == Decimal(25000)
    assert resolved.option_type == "CE"
    assert resolved.expiry == expiry
    assert resolved.exchange == "NFO"
    assert "25000CE" in resolved.tradingsymbol


def test_resolve_option_otm_put():
    expiry = date(2026, 7, 28)
    rows = _nifty_chain_for_expiry(expiry, [24900, 24950, 25000, 25050, 25100], 7000)
    resolved = resolve_option(
        rows, "NIFTY", "this_week", strike_offset=-2, option_type="PE",
        spot_price=Decimal(25000), as_of=TODAY,
    )
    assert resolved.strike == Decimal(24900)
    assert resolved.option_type == "PE"


def test_resolve_option_invalid_option_type_raises():
    with pytest.raises(ValueError, match="option_type must be"):
        resolve_option([], "NIFTY", "this_week", 0, "XX", Decimal(25000), as_of=TODAY)


def test_resolve_option_no_matching_instruments_raises():
    expiry = date(2026, 7, 28)
    rows = _nifty_chain_for_expiry(expiry, [25000], 8000)
    # Ask for BANKNIFTY when only NIFTY rows exist for this expiry.
    with pytest.raises(ExpirySelectionError):
        resolve_option(rows, "BANKNIFTY", "this_week", 0, "CE", Decimal(52000), as_of=TODAY)
