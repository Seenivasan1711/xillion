"""data/import_mt5_csv.py -- MT5 export -> UTC M1 mid bars (2026-09-25)."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parent.parent / "data" / "import_mt5_csv.py"
_spec = importlib.util.spec_from_file_location("import_mt5_csv", _PATH)
im = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(im)

TICK_HEADER = "<DATE>\t<TIME>\t<BID>\t<ASK>\t<LAST>\t<VOLUME>\t<FLAGS>\r\n"


def _write_ticks(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    # rows: (server datetime, bid or "", ask or "") -- sparse like the real export
    lines = [TICK_HEADER]
    for dt, bid, ask in rows:
        d, t = dt.split(" ")
        lines.append(f"{d}\t{t}\t{bid}\t{ask}\t\t\t6\r\n")
    path.write_text("".join(lines))
    return path


def test_server_time_is_utc_plus_3_in_summer_and_plus_2_in_winter():
    s = pd.Series(pd.to_datetime(["2026-07-01 03:00:00", "2026-01-15 02:00:00"]))
    utc = im.server_to_utc(s, "ny+7")
    assert list(utc.dt.hour) == [0, 0]


def test_ny7_and_eet_differ_only_between_the_us_and_eu_dst_switches():
    # 2026-03-16: US already on DST (Mar 8), EU not yet (Mar 29)
    s = pd.Series(pd.to_datetime(["2026-03-16 12:00:00"]))
    assert im.server_to_utc(s, "ny+7").dt.hour.iloc[0] == 9
    assert im.server_to_utc(s, "eet").dt.hour.iloc[0] == 10


def test_sparse_ticks_are_forward_filled_and_bars_built_from_mid(tmp_path):
    p = _write_ticks(tmp_path / "t.csv", [
        ("2026.07.01 03:00:01.000", "100.00", "100.20"),
        ("2026.07.01 03:00:30.000", "101.00", ""),      # bid-only: ask stays 100.20
        ("2026.07.01 03:01:05.000", "", "101.40"),      # ask-only: bid stays 101.00
    ])
    bars = im.import_ticks(p, point=0.01, server_tz="ny+7")
    assert len(bars) == 2
    b0, b1 = bars.iloc[0], bars.iloc[1]
    assert str(b0.ts) == "2026-07-01 00:00:00+00:00"
    assert b0.open == pytest.approx(100.10) and b0.close == pytest.approx(100.60)
    assert b0.volume == 2
    assert b1.close == pytest.approx(101.20)
    assert b1.spread_pts == pytest.approx(40)


def test_chunked_import_matches_one_shot(tmp_path, monkeypatch):
    rows = []
    for i in range(600):  # 10 minutes of 1-second ticks, both sides alternating sparse
        dt = f"2026.07.01 03:{i // 60:02d}:{i % 60:02d}.000"
        px = f"{100 + (i % 37) * 0.01:.2f}"
        rows.append((dt, px, "") if i % 3 else (dt, px, f"{float(px) + 0.15:.2f}"))
    p = _write_ticks(tmp_path / "t.csv", rows)
    monkeypatch.setattr(im, "CHUNK_ROWS", 10_000)
    whole = im.import_ticks(p, 0.01, "ny+7")
    monkeypatch.setattr(im, "CHUNK_ROWS", 47)  # boundaries land mid-minute
    chunked = im.import_ticks(p, 0.01, "ny+7")
    pd.testing.assert_frame_equal(whole, chunked)


def test_bar_export_is_shifted_from_bid_to_mid(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\r\n"
        "2026.07.01\t03:00:00\t100.00\t101.00\t99.00\t100.50\t40\t0\t20\r\n"
    )
    assert im.detect_kind(p) == "bars"
    b = im.import_bars(p, 0.01, "ny+7").iloc[0]
    assert str(b.ts) == "2026-07-01 00:00:00+00:00"
    assert b.close == pytest.approx(100.60) and b.low == pytest.approx(99.10)


def test_tick_bars_win_over_bar_export_for_the_same_minute(tmp_path):
    ts = pd.to_datetime(["2026-07-01 00:00"], utc=True)
    frame = lambda px: pd.DataFrame({"ts": ts, "open": px, "high": px, "low": px, "close": px,
                                     "volume": 1.0, "spread_pts": 10.0})
    im.write_monthly(frame(2.0), "XAUUSD", tmp_path, overwrite_ticks=True)
    im.write_monthly(frame(1.0), "XAUUSD", tmp_path, overwrite_ticks=False)
    out = pd.read_parquet(tmp_path / "XAUUSD_2026-07.parquet")
    assert list(out.close) == [2.0]


def test_data_source_env_selects_the_mt5_directory(monkeypatch):
    from research.xauusd_scalping.engine.instruments import get_instrument

    monkeypatch.delenv("RESEARCH_DATA_SOURCE", raising=False)
    assert get_instrument("XAUUSD").data_dir.name == "xauusd"
    monkeypatch.setenv("RESEARCH_DATA_SOURCE", "mt5")
    assert get_instrument("XAUUSD").data_dir.name == "xauusd_mt5"
    monkeypatch.setenv("RESEARCH_DATA_SOURCE", "bogus")
    with pytest.raises(ValueError):
        get_instrument("XAUUSD").data_dir
