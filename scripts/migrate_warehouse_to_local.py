"""
One-off migration: copy bar / bar_coverage / option_chain_snapshot from
whatever DATABASE_URL currently points at (Supabase, in practice) into the
new local warehouse DB (get_warehouse_session_factory -- see
Settings.backtest_database_url).

Why this exists: these three tables are 100% regenerable backtest/
historical cache, but they'd already grown to ~1.5GB before anyone noticed
-- 98% of Supabase's free-tier usage, 2026-08-26. Rather than just deleting
them and re-running the (slow, network-bound) bhavcopy backfill from
scratch, this copies the DATA that's already there straight from the old
DB to the new one -- much faster than re-fetching, and the source is
truncated (scripts/truncate_supabase_warehouse.py) only after this confirms
row counts match.

Uses Core (raw dict rows via SQLAlchemy `select`/`insert`), not the ORM --
at millions of rows, hydrating ORM objects per row would be far slower and
much more memory-hungry than moving plain dicts in batches.

Keyset (not OFFSET) pagination: `bar` alone is 4.5M+ rows, and OFFSET's
cost grows with the offset itself (Postgres re-scans and discards every
prior row on each page) -- quadratic overall, and far too slow at this
size. Paginating on each table's natural key via `WHERE (key) > (last)`
instead keeps every page's cost roughly constant.

Usage:
    python scripts/migrate_warehouse_to_local.py
"""

import asyncio
from decimal import Decimal

import typer
from sqlalchemy import column, table, tuple_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

app = typer.Typer()


def _sqlite_safe(row: dict) -> dict:
    """aiosqlite can't bind a raw decimal.Decimal parameter (Postgres/
    asyncpg hands Numeric columns back as Decimal; SQLite has no native
    decimal type) -- convert to float, matching how these columns are
    already typed on the Python side (BarRecord.open etc are Mapped[float]
    despite the DB column being Numeric)."""
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


_BATCH_SIZE = 5000

# (Core table handle, ordered key columns for keyset pagination) -- avoids
# importing xillion.db.models and hydrating an ORM object per row.
_TABLES: dict[str, tuple] = {
    "bar_coverage": (
        table(
            "bar_coverage",
            column("symbol"),
            column("exchange"),
            column("timeframe"),
            column("provider_name"),
            column("from_date"),
            column("to_date"),
            column("updated_at"),
        ),
        ["symbol", "exchange", "timeframe", "provider_name"],
    ),
    "bar": (
        table(
            "bar",
            column("symbol"),
            column("exchange"),
            column("timeframe"),
            column("ts"),
            column("open"),
            column("high"),
            column("low"),
            column("close"),
            column("volume"),
        ),
        ["symbol", "exchange", "timeframe", "ts"],
    ),
    "option_chain_snapshot": (
        table(
            "option_chain_snapshot",
            column("trade_date"),
            column("exchange"),
            column("tradingsymbol"),
            column("underlying"),
            column("expiry"),
            column("strike"),
            column("option_type"),
            column("lot_size"),
            column("close"),
            column("underlying_price"),
        ),
        ["trade_date", "exchange", "tradingsymbol"],
    ),
}


@app.command()
def main() -> None:
    async def _run() -> None:
        from sqlalchemy import func, select

        from xillion.db.session import (
            get_session_factory,
            get_warehouse_session_factory,
            init_warehouse_db,
        )

        await init_warehouse_db()
        src_factory = get_session_factory()
        dst_factory = get_warehouse_session_factory()

        for name, (tbl, key_cols) in _TABLES.items():
            key = [getattr(tbl.c, c) for c in key_cols]

            async with src_factory() as src:
                total = (await src.execute(select(func.count()).select_from(tbl))).scalar_one()
            print(f"{name}: {total} rows in source")
            if total == 0:
                continue

            copied = 0
            last = None
            async with src_factory() as src, dst_factory() as dst:
                while True:
                    stmt = select(tbl).order_by(*key).limit(_BATCH_SIZE)
                    if last is not None:
                        stmt = stmt.where(tuple_(*key) > tuple(last))
                    result = await src.execute(stmt)
                    rows = [_sqlite_safe(dict(r._mapping)) for r in result.fetchall()]
                    if not rows:
                        break
                    last_row = rows[-1]
                    last = tuple(last_row[c] for c in key_cols)

                    insert_stmt = sqlite_insert(tbl).values(rows)
                    await dst.execute(insert_stmt)
                    await dst.commit()
                    copied += len(rows)
                    if copied % (_BATCH_SIZE * 10) == 0 or copied >= total:
                        print(f"  {name}: {copied}/{total}", flush=True)
                    if len(rows) < _BATCH_SIZE:
                        break

            async with dst_factory() as dst:
                dst_total = (await dst.execute(select(func.count()).select_from(tbl))).scalar_one()
            status = "OK" if dst_total == total else "MISMATCH"
            print(f"{name}: {dst_total} rows in destination ({status})")
            if dst_total != total:
                raise typer.Exit(1)

        print("Migration complete -- verify row counts above before truncating the source.")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
