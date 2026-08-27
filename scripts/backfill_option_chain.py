"""
Backfill xillion.db.models.OptionChainSnapshot (the table
xillion.data.option_chain.OptionChainWarehouse reads from) for a date range.

Why this is a separate script from scripts/backfill.py: that script fills
`bar`/`bar_coverage` via BarWarehouse, which options/multi-leg strategies
(CreditSpreadWeeklyStrategy et al, driven by BacktestEngine's
ctx.get_spot()/resolve_strike()/get_option_price()) do NOT read from --
those calls require an OptionChainWarehouse backed by OptionChainSnapshot,
a genuinely different table with a different (point-in-time full chain)
shape. Found 2026-08-26 while trying to run the real multi-year credit-
spread pass/fail backtest (docs/strategies/knowledge-base/
10-FIRST-STRATEGY-SPEC.md #10): despite `bar` already having 2021-2026
per-contract option OHLC from the earlier backfill, OptionChainSnapshot had
zero rows -- the two tables were never actually wired together.

Resumable: skips any (exchange, day) already present via
OptionChainRepository.has_any_for_day, same pattern scripts/backfill.py
uses via bar_coverage. A holiday (zero rows returned) is NOT recorded as
"done" and will be re-attempted on a re-run -- cheap (one fast 404) and
simpler than adding a second holiday-tracking table for a script meant to
run once.

Usage:
    python scripts/backfill_option_chain.py --from 2021-01-01 --to 2026-08-25 \
        --underlying-filter NIFTY,BANKNIFTY
"""

import asyncio
from datetime import date, timedelta

import typer

app = typer.Typer()


@app.command()
def main(
    from_date: str = typer.Option(..., "--from", help="YYYY-MM-DD, inclusive"),
    to_date: str = typer.Option(..., "--to", help="YYYY-MM-DD, inclusive"),
    underlying_filter: str = typer.Option(
        "NIFTY,BANKNIFTY",
        "--underlying-filter",
        help="Comma-separated underlyings to keep from each day's whole-file "
        "fetch. Matches scripts/backfill.py's scoping so the two tables "
        "cover the same underlyings.",
    ),
) -> None:
    filter_set = {s.strip() for s in underlying_filter.split(",") if s.strip()} or None

    async def _run() -> None:
        import structlog

        from data_providers.nse_bhavcopy import NSEBhavcopyProvider
        from xillion.data.option_chain import OptionChainRepository, OptionChainWarehouse
        from xillion.db.session import get_warehouse_session_factory, init_warehouse_db

        logger = structlog.get_logger(__name__)
        # option_chain_snapshot lives in the warehouse DB (a plain local
        # SQLite file, never Alembic-managed) -- see
        # Settings.backtest_database_url and scripts/backfill.py's identical
        # note.
        await init_warehouse_db()
        factory = get_warehouse_session_factory()
        repo = OptionChainRepository(factory)
        base_provider = NSEBhavcopyProvider()

        class _FilteredProvider:
            """Wraps the real provider, keeping only underlying_filter's
            rows before they reach the DB -- fetch_option_chain_for_day has
            no filter param of its own (unlike fetch_bars_bulk), so this is
            applied here rather than duplicating fetch/parse logic."""

            async def fetch_option_chain_for_day(self, day: date) -> list:
                rows = await base_provider.fetch_option_chain_for_day(day)
                if filter_set is None:
                    return rows
                return [r for r in rows if r.underlying in filter_set]

        warehouse = OptionChainWarehouse(_FilteredProvider(), repo)

        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        total_days = (end - start).days + 1
        day = start
        fetched, skipped, empty = 0, 0, 0
        i = 0
        while day <= end:
            i += 1
            if day.weekday() >= 5:
                day += timedelta(days=1)
                continue
            # A ~1450-day loop run over hours is long enough to outlast more
            # than one kind of transient failure -- hit twice for real
            # 2026-08-26: a stale pooled connection (session.py's
            # pool_pre_ping now covers that specific case) and separately a
            # bare ConnectionResetError during a *fresh* connection's SSL
            # handshake, from has_any_for_day (outside the old retry's
            # scope, so it crashed the whole run uncaught). Both the
            # has_any_for_day check and the fetch are inside the retry now,
            # with more attempts and longer backoff given how long this run
            # needs to survive.
            rows: list = []
            for attempt in range(5):
                try:
                    already = await repo.has_any_for_day("NFO", day)
                    if already:
                        skipped += 1
                        rows = []
                    else:
                        rows = await warehouse.get_chain("NIFTY", "NFO", day)
                        if rows:
                            fetched += 1
                        else:
                            empty += 1
                    break
                except Exception as exc:
                    if attempt == 4:
                        logger.error(
                            "option chain backfill: day failed after retries, skipping",
                            day=str(day),
                            error=str(exc),
                        )
                        empty += 1
                        break
                    logger.warning(
                        "option chain backfill: retrying day",
                        day=str(day),
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                    await asyncio.sleep(5 * (attempt + 1))
            if i % 50 == 0 or day == end:
                logger.info(
                    "option chain backfill progress",
                    day=str(day),
                    pct=round(100 * i / total_days, 1),
                    fetched=fetched,
                    skipped=skipped,
                    empty=empty,
                )
            day += timedelta(days=1)

        logger.info(
            "option chain backfill complete",
            fetched=fetched,
            skipped_already_done=skipped,
            empty_or_holiday=empty,
        )

    asyncio.run(_run())


if __name__ == "__main__":
    app()
