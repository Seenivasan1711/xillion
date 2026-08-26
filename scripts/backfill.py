#!/usr/bin/env python
"""
Run a historical backfill through BarWarehouse -- the offline counterpart to
POST /api/data/backfill, meant for the real multi-year run (CP3's "run the
real 2-5 year backfill", which can run for a long time and shouldn't block
an HTTP request or a browser tab).

Chunked by year so a mid-run failure (network blip, rate limit) only loses
one year's progress -- everything before it is already committed to
bar_coverage and won't be re-fetched on retry.

Example (NSE bhavcopy needs no credentials, so this can run standalone):
  python scripts/backfill.py --provider "NSE Bhavcopy (Free)" \
      --symbol NIFTY26AUGFUT --exchange NFO --instrument-type future \
      --from-date 2023-01-01 --to-date 2026-08-24
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).parent.parent))

app = typer.Typer()


def _year_chunks(from_date: date, to_date: date):
    year = from_date.year
    while year <= to_date.year:
        chunk_from = max(from_date, date(year, 1, 1))
        chunk_to = min(to_date, date(year, 12, 31))
        yield chunk_from, chunk_to
        year += 1


@app.command()
def main(
    provider: str = typer.Option(
        ..., "--provider", help="Data provider name, e.g. 'NSE Bhavcopy (Free)'"
    ),
    symbol: str = typer.Option(
        ...,
        "--symbol",
        help="Full tradingsymbol (ignored for whole-file-bulk providers' own persistence, but still used to report bars found)",
    ),
    exchange: str = typer.Option("NFO", "--exchange"),
    instrument_type: str = typer.Option("option", "--instrument-type"),
    timeframe: str = typer.Option("1d", "--timeframe"),
    from_date: str = typer.Option(..., "--from-date", help="YYYY-MM-DD"),
    to_date: str = typer.Option(..., "--to-date", help="YYYY-MM-DD"),
    underlying_filter: str = typer.Option(
        "",
        "--underlying-filter",
        help=(
            "Comma-separated underlyings (e.g. 'NIFTY,BANKNIFTY') to keep from a "
            "whole-file-bulk provider's daily file. A real multi-year NFO backfill "
            "with no filter is ~85M+ rows across every contract on the exchange -- "
            "this scopes storage down to what a specific strategy actually trades. "
            "Ignored for non-bulk providers (they only ever fetch the one --symbol)."
        ),
    ),
) -> None:
    """Backfill one symbol's history, year by year, resumable on failure."""
    filter_set = {s.strip() for s in underlying_filter.split(",") if s.strip()} or None

    async def _run() -> None:
        from xillion.auth.data_provider_credstore import load_provider_credentials
        from xillion.config import get_settings
        from xillion.core.plugin_loader import PluginLoader
        from xillion.data.coverage import BarCoverageRepository
        from xillion.data.repository import BarRepository
        from xillion.data.warehouse import BarWarehouse
        from xillion.db.session import get_session_factory, init_db

        if get_settings().is_production:
            # Same guard as xillion/main.py's lifespan: production schema is
            # owned by Alembic, not create_all(). Calling init_db()
            # unconditionally here against a real (production-pointed) DB is
            # exactly what desynced alembic_version from the actual schema
            # once already -- create_all() silently creates whatever tables
            # the current models.py defines without ever updating Alembic's
            # own version-tracking row, so a later `alembic upgrade head`
            # elsewhere (e.g. a fresh Render deploy) sees an old revision,
            # tries to recreate tables that already exist, and crashes with
            # "relation already exists".
            print(
                "production DATABASE_URL detected -- skipping create_all(), schema is Alembic-managed",
                file=sys.stderr,
            )
        else:
            await init_db()
        loader = PluginLoader()
        registry = await loader.discover_all()
        provider_cls = registry.data_providers.get(provider)
        if provider_cls is None:
            print(
                f"Provider '{provider}' not found. Available: {list(registry.data_providers)}",
                file=sys.stderr,
            )
            raise typer.Exit(1)

        provider_instance = provider_cls()
        credentials = None
        if provider_instance.capabilities.requires_credentials:
            factory = get_session_factory()
            async with factory() as session:
                credentials = await load_provider_credentials(session, provider)
            if credentials is None:
                print(
                    f"'{provider}' needs credentials — set them via Settings → Data Providers first.",
                    file=sys.stderr,
                )
                raise typer.Exit(1)

        factory = get_session_factory()
        warehouse = BarWarehouse(BarRepository(factory), BarCoverageRepository(factory))

        f = date.fromisoformat(from_date)
        t = date.fromisoformat(to_date)
        total_bars = 0
        for chunk_from, chunk_to in _year_chunks(f, t):
            print(f"Backfilling {chunk_from} → {chunk_to} ...", flush=True)
            try:
                bars = await warehouse.get_bars(
                    provider_instance,
                    symbol,
                    exchange,
                    timeframe,
                    chunk_from,
                    chunk_to,
                    instrument_type=instrument_type,
                    credentials=credentials,
                    broker=None,
                    underlying_filter=filter_set,
                )
            except Exception as exc:
                print(f"  FAILED {chunk_from}-{chunk_to}: {exc}", file=sys.stderr)
                print(
                    "  Progress up to this point is already committed. Re-run the same "
                    "command to resume — earlier years won't be re-fetched.",
                    file=sys.stderr,
                )
                raise typer.Exit(1) from exc
            total_bars = len(bars)  # cumulative count for this symbol so far
            print(f"  {chunk_to.year}: {len(bars)} bars now covering {f}-{chunk_to}", flush=True)

        print(f"Done. {symbol} now has {total_bars} bars covering {f} → {t}.")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
