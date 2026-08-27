"""
Truncate bar / bar_coverage / option_chain_snapshot on whatever
get_session_factory() (i.e. DATABASE_URL) currently points at -- run this
ONLY after scripts/migrate_warehouse_to_local.py has confirmed the local
warehouse DB has a matching row count for every table. This is what
actually reclaims the ~1.5GB of Supabase free-tier space these tables were
using (2026-08-26) -- the data itself is 100% regenerable free from NSE
Bhavcopy, and now lives in the local warehouse DB
(get_warehouse_session_factory) instead.

TRUNCATE, not DROP: the tables/schema stay (Alembic still tracks them),
just emptied. Requires typing "yes" to confirm -- this deletes real rows
from the shared production DB Render also points at.

Usage:
    python scripts/truncate_supabase_warehouse.py
"""

import asyncio

import typer
from sqlalchemy import text

app = typer.Typer()

_TABLES = ["bar", "bar_coverage", "option_chain_snapshot"]


@app.command()
def main() -> None:
    async def _run() -> None:
        from sqlalchemy import func, select, table

        from xillion.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            for name in _TABLES:
                count = (
                    await db.execute(select(func.count()).select_from(table(name)))
                ).scalar_one()
                print(f"{name}: {count} rows currently in source")

        confirm = input(
            f"\nThis will TRUNCATE {_TABLES} on the DB DATABASE_URL points at. "
            "Only do this after migrate_warehouse_to_local.py confirmed matching "
            "row counts. Type 'yes' to proceed: "
        )
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            raise typer.Exit(1)

        async with factory() as db:
            for name in _TABLES:
                await db.execute(text(f'TRUNCATE TABLE "{name}"'))
            await db.commit()
        print("Truncated:", ", ".join(_TABLES))

    asyncio.run(_run())


if __name__ == "__main__":
    app()
