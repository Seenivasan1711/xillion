"""
My Trades (2026-09-26): MT5 History-report parsing and the import / manual
entry / tagging / stats routes, driven directly against a real in-memory DB
(same pattern as test_proposed_changes.py).
"""

import io

import pytest
from fastapi import HTTPException, UploadFile

from xillion.api.my_trades import (
    ManualTrade,
    TradeTags,
    create_trade,
    delete_trade,
    import_mt5_report,
    list_trades,
    r_multiple,
    tag_trade,
    trade_stats,
)
from xillion.db.models import MyTrade
from xillion.db.session import get_session_factory, init_db
from xillion.engine.mt5_history_report import parse_account, parse_positions


class _User:
    username = "rakesh"


HEAD = (
    "<tr><td>Time</td><td>Position</td><td>Symbol</td><td>Type</td><td>Volume</td><td>Price</td>"
    "<td>S / L</td><td>T / P</td><td>Time</td><td>Price</td><td>Commission</td><td>Swap</td><td>Profit</td></tr>"
)


def _report(rows: list[str], encoding="utf-16") -> bytes:
    html = (
        "<html><body><table>"
        "<tr><td colspan=13>Trade History Report</td></tr>"
        "<tr><td colspan=3>Account:</td><td colspan=10>112555079 (USD, MetaQuotes-Demo, demo, Hedge)</td></tr>"
        "<tr><td colspan=13>Positions</td></tr>"
        + HEAD
        + "".join(rows)
        + "<tr><td colspan=13>Orders</td></tr>"
        "<tr><td>2026.08.25 07:12:58</td><td>67996977</td><td>XAUUSD</td><td>buy</td></tr>"
        "</table></body></html>"
    )
    return html.encode(encoding)


# The two real trades from Rakesh's MT5 History screenshot (2026-09-25).
ROW_BUY = (
    "<tr><td>2026.08.25 07:12:58</td><td>67996977</td><td>XAUUSD</td><td>buy</td><td>0.10</td>"
    "<td>4 637.49</td><td>4 628.10</td><td>4 683.03</td><td>2026.08.25 07:15:07</td><td>4 636.64</td>"
    "<td>-0.50</td><td>0.00</td><td>-8.50</td></tr>"
)
ROW_SELL = (
    "<tr><td>2026.08.25 07:15:11</td><td>67997882</td><td>XAUUSD</td><td>sell</td><td>0.10</td>"
    "<td>4 636.43</td><td>4 637.91</td><td>4 631.74</td><td>2026.08.25 07:16:06</td><td>4 635.65</td>"
    "<td>-0.50</td><td>0.00</td><td>7.80</td></tr>"
)


def test_parse_real_screenshot_rows_utf16_with_space_thousands():
    pos, warnings = parse_positions(_report([ROW_BUY, ROW_SELL]))
    assert warnings == [] and len(pos) == 2
    b = pos[0]
    assert (b.ticket, b.side, b.volume_lots, b.open_price, b.stop_loss) == (
        "67996977",
        "BUY",
        0.10,
        4637.49,
        4628.10,
    )
    assert b.commission == -0.50 and b.profit == -8.50
    # 07:12:58 EEST (UTC+3 in August) -> 04:12:58 UTC; the Orders section is ignored
    assert b.open_time == "2026-08-25T04:12:58+00:00"
    # sanity: the reported profit matches the price move (0.85 x 0.10 lot x 100 oz)
    assert round((b.close_price - b.open_price) * 0.10 * 100, 2) == b.profit


def test_parse_winter_time_and_utf8():
    row = ROW_BUY.replace("2026.08.25", "2026.01.15")
    pos, _ = parse_positions(_report([row], encoding="utf-8"))
    assert pos[0].open_time == "2026-01-15T05:12:58+00:00"  # EET = UTC+2


def test_not_a_report_is_rejected():
    with pytest.raises(ValueError):
        parse_positions(b"<html><table><tr><td>hello</td></tr></table></html>")


def _upload(data: bytes) -> UploadFile:
    return UploadFile(filename="ReportHistory.html", file=io.BytesIO(data))


@pytest.mark.asyncio
async def test_import_is_idempotent_and_keeps_tags():
    await init_db()
    async with get_session_factory()() as db:
        await db.execute(MyTrade.__table__.delete())
        await db.commit()

        dry = await import_mt5_report(
            _upload(_report([ROW_BUY, ROW_SELL])), "fundingpips", True, db, _User()
        )
        assert (dry["added"], dry["dry_run"]) == (2, True)
        assert await list_trades(None, None, db, _User()) == []

        res = await import_mt5_report(
            _upload(_report([ROW_BUY, ROW_SELL])), "fundingpips", False, db, _User()
        )
        assert (res["added"], res["updated"]) == (2, 0)
        trades = await list_trades(None, None, db, _User())
        buy = next(t for t in trades if t["external_id"] == "67996977")
        assert buy["net_pnl"] == pytest.approx(-9.0)
        await tag_trade(
            buy["id"], TradeTags(setup_tag="PDH sweep", followed_plan=True), db, _User()
        )

        again = await import_mt5_report(
            _upload(_report([ROW_BUY, ROW_SELL])), "fundingpips", False, db, _User()
        )
        assert (again["added"], again["updated"]) == (0, 2)
        trades = await list_trades(None, None, db, _User())
        assert len(trades) == 2
        assert next(t for t in trades if t["external_id"] == "67996977")["setup_tag"] == "PDH sweep"

        with pytest.raises(HTTPException) as exc:
            await delete_trade(buy["id"], db, _User())
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_manual_trade_r_multiple_and_stats():
    await init_db()
    async with get_session_factory()() as db:
        await db.execute(MyTrade.__table__.delete())
        await db.commit()
        # risk: $5 stop x 0.05 lot x 100 oz = $25; net +$50 -> +2R
        t = await create_trade(
            ManualTrade(
                side="buy",
                volume_lots=0.05,
                open_time="2026-09-01T08:00:00",
                open_price=2000.0,
                stop_loss=1995.0,
                close_price=2010.2,
                profit=51.0,
                commission=-0.5,
                swap=-0.5,
                setup_tag="London ORB",
                followed_plan=True,
            ),
            db,
            _User(),
        )
        assert t["side"] == "BUY" and t["open_time"] == "2026-09-01T08:00:00+00:00"
        assert t["r_multiple"] == pytest.approx(2.0)
        await create_trade(
            ManualTrade(
                side="sell",
                volume_lots=0.05,
                open_time="2026-09-02T08:00:00",
                open_price=2000.0,
                stop_loss=2005.0,
                profit=-25.0,
                setup_tag="London ORB",
                followed_plan=False,
            ),
            db,
            _User(),
        )
        s = await trade_stats(None, db, _User())
        orb = s["by_setup"]["London ORB"]
        assert (
            orb["n"] == 2 and orb["win_rate"] == 50.0 and orb["profit_factor"] == pytest.approx(2.0)
        )
        assert orb["avg_r"] == pytest.approx(0.5)
        assert (
            s["followed_plan"]["yes"]["net_pnl"] == 50.0
            and s["followed_plan"]["no"]["net_pnl"] == -25.0
        )
        with pytest.raises(HTTPException):
            await create_trade(
                ManualTrade(
                    side="hold", volume_lots=1, open_time="2026-09-01T08:00:00", open_price=1.0
                ),
                db,
                _User(),
            )


def test_r_multiple_unknown_symbol_is_none():
    t = MyTrade(
        symbol="US30",
        side="BUY",
        volume_lots=1,
        open_price=100,
        stop_loss=90,
        profit=10,
        commission=0,
        swap=0,
    )
    assert r_multiple(t) is None


def test_account_header_and_an_empty_real_style_report():
    # Structure copied from Rakesh's real (empty, demo) report, 2026-09-26:
    # Positions/Orders/Deals headers with no position rows, then a balance deal.
    raw = _report([])
    acct = parse_account(raw)
    assert (acct.login, acct.server, acct.is_demo) == ("112555079", "MetaQuotes-Demo", True)
    pos, warnings = parse_positions(raw)
    assert pos == [] and warnings == []


class _Notifier:
    def __init__(self):
        self.alerts = []

    async def alert(self, title, body, severity="info"):
        self.alerts.append((title, body, severity))
        return 1


class _App:
    def __init__(self, notifier):
        self.state = type("S", (), {"telegram": notifier})()


class _Req:
    def __init__(self, notifier):
        self.app = _App(notifier)


@pytest.mark.asyncio
async def test_manual_trade_crossing_the_daily_stop_warns_once():
    from datetime import UTC, datetime, timedelta

    from xillion.api.prop_account import get_status

    await init_db()
    async with get_session_factory()() as db:
        await db.execute(MyTrade.__table__.delete())
        await db.commit()
        n = _Notifier()
        now = datetime.now(UTC).replace(microsecond=0)
        opened = (now - timedelta(hours=1)).isoformat()
        closed = now.isoformat()

        def trade(pnl):
            return ManualTrade(
                side="buy",
                volume_lots=0.01,
                open_time=opened,
                open_price=4000.0,
                close_time=closed,
                close_price=4000.0,
                profit=pnl,
            )

        await create_trade(trade(-20.0), db, _User(), request=_Req(n))
        assert n.alerts == []  # 40% of the $50 stop
        await create_trade(trade(-22.0), db, _User(), request=_Req(n))
        assert (
            len(n.alerts) == 1 and "Your daily stop" in n.alerts[0][1] and n.alerts[0][2] == "warn"
        )
        await create_trade(trade(-1.0), db, _User(), request=_Req(n))
        assert len(n.alerts) == 1  # still "warn": no repeat
        await create_trade(trade(-10.0), db, _User(), request=_Req(n))
        assert len(n.alerts) == 2 and n.alerts[1][2] == "critical" and "BREACHED" in n.alerts[1][1]

        st = await get_status(db, _User())
        assert st["today_pnl"] == -53.0 and st["level"] == "breach"
        assert st["basis"].startswith("closed trades only")
