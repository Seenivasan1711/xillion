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
        "NIFTY,BANKNIFTY", "--underlying-filter",
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
        from xillion.db.session import get_session_factory, init_db

        logger = structlog.get_logger(__name__)
        await init_db()
        factory = get_session_factory()
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
            already = await repo.has_any_for_day("NFO", day)
            if already:
                skipped += 1
            else:
                # A ~1450-day loop is long enough to outlast a single flaky
                # connection or transient fetch failure (hit for real
                # 2026-08-26, ~8 days in: Supabase's pooler dropped an idle
                # connection mid-query -- session.py now sets pool_pre_ping
                # for that specific case, but this retries anything else
                # transient too rather than dying at 4am with 1400 days left).
                for attempt in range(3):
                    try:
                        rows = await warehouse.get_chain("NIFTY", "NFO", day)
                        break
                    except Exception as exc:
                        if attempt == 2:
                            logger.error("option chain backfill: day failed, skipping", day=str(day), error=str(exc))
                            rows = []
                            break
                        logger.warning("option chain backfill: retrying day", day=str(day), attempt=attempt + 1, error=str(exc))
                        await asyncio.sleep(3)
                if rows:
                    fetched += 1
                else:
                    empty += 1
            if i % 50 == 0 or day == end:
                logger.info(
                    "option chain backfill progress",
                    day=str(day), pct=round(100 * i / total_days, 1),
                    fetched=fetched, skipped=skipped, empty=empty,
                )
            day += timedelta(days=1)

        logger.info(
            "option chain backfill complete",
            fetched=fetched, skipped_already_done=skipped, empty_or_holiday=empty,
        )

    asyncio.run(_run())


if __name__ == "__main__":
    app()
