"""
Dhan scrip-master resolution (shared by data_providers/dhanhq.py and
brokers/dhan.py, CP15). Real header + rows below are copied verbatim from a
live fetch of https://images.dhan.co/api-data/api-scrip-master-detailed.csv
(2026-08-25), not guessed.
"""
import io
from pathlib import Path

import pytest

from xillion.core.dhan_instruments import (
    EXCHANGE_SEGMENT_TO_FEED_CODE, exchange_segment, resolve_security,
)

_REAL_HEADER = (
    "EXCH_ID,SEGMENT,SECURITY_ID,ISIN,INSTRUMENT,UNDERLYING_SECURITY_ID,UNDERLYING_SYMBOL,"
    "SYMBOL_NAME,DISPLAY_NAME,INSTRUMENT_TYPE,SERIES,LOT_SIZE,SM_EXPIRY_DATE,STRIKE_PRICE,"
    "OPTION_TYPE,TICK_SIZE,EXPIRY_FLAG,BRACKET_FLAG,COVER_FLAG,ASM_GSM_FLAG,ASM_GSM_CATEGORY,"
    "BUY_SELL_INDICATOR,BUY_CO_MIN_MARGIN_PER,BUY_CO_SL_RANGE_MAX_PERC,BUY_CO_SL_RANGE_MIN_PERC,"
    "BUY_BO_MIN_MARGIN_PER,BUY_BO_PROFIT_RANGE_MAX_PERC,BUY_BO_PROFIT_RANGE_MIN_PERC,MTF_LEVERAGE,"
    "SM_UPPER_LIMIT,SM_LOWER_LIMIT,SM_FREEZE_QTY,"
)
_REAL_FUTCUR_ROW = (
    "BSE,C,1026077,NA,FUTCUR,600,USDINR,USDINR,USDINR AUG FUT,FUTCUR,NA,1.0,2024-08-28,"
    "-0.01000,XX,0.2500,M,N,N,N,NA,A,0,0,0,0,0,0,0,86.4500,81.4100,701,"
)


def _write_master(tmp_path: Path, extra_rows: list[str]) -> Path:
    p = tmp_path / "scrip_master.csv"
    p.write_text(_REAL_HEADER + "\n" + "\n".join(extra_rows) + "\n")
    return p


def test_exchange_segment_index():
    assert exchange_segment("NSE", "INDEX") == "IDX_I"


def test_exchange_segment_nse_equity():
    assert exchange_segment("NSE", "EQUITY") == "NSE_EQ"


def test_exchange_segment_nse_options():
    assert exchange_segment("NSE", "OPTIDX") == "NSE_FNO"
    assert exchange_segment("NSE", "OPTSTK") == "NSE_FNO"


def test_exchange_segment_bse_futures():
    assert exchange_segment("BSE", "FUTIDX") == "BSE_FNO"


def test_exchange_segment_mcx():
    assert exchange_segment("MCX", "FUTCOM") == "MCX_COMM"


def test_exchange_segment_unknown_raises():
    with pytest.raises(ValueError):
        exchange_segment("XYZ", "WHATEVER")


def test_resolve_security_reads_real_columns(tmp_path):
    master = _write_master(tmp_path, [_REAL_FUTCUR_ROW])
    resolved = resolve_security(master, "USDINR")
    assert resolved is not None
    assert resolved.security_id == "1026077"
    assert resolved.instrument == "FUTCUR"
    assert resolved.lot_size == 1
    assert resolved.tick_size == "0.2500"


def test_resolve_security_matches_by_display_name_too(tmp_path):
    master = _write_master(tmp_path, [_REAL_FUTCUR_ROW])
    resolved = resolve_security(master, "USDINR AUG FUT")
    assert resolved is not None
    assert resolved.security_id == "1026077"


def test_resolve_security_returns_none_when_not_found(tmp_path):
    master = _write_master(tmp_path, [_REAL_FUTCUR_ROW])
    assert resolve_security(master, "NOT_A_REAL_SYMBOL") is None


def test_feed_code_mapping_covers_all_exchange_segments():
    # Every string exchangeSegment exchange_segment() can produce must have
    # a numeric feed code -- otherwise subscribe_ticks silently drops it.
    produced = {"IDX_I", "NSE_EQ", "NSE_FNO", "NSE_CURRENCY", "BSE_EQ", "BSE_FNO", "BSE_CURRENCY", "MCX_COMM"}
    assert produced.issubset(EXCHANGE_SEGMENT_TO_FEED_CODE.keys())
