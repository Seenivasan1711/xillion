#!/usr/bin/env python
"""Create the data directory and initialise the database."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    Path("data").mkdir(exist_ok=True)
    from xillion.config import get_settings
    from xillion.db.session import init_db

    if get_settings().is_production:
        # create_all() bypasses Alembic's version tracking entirely -- run
        # against a production-pointed DATABASE_URL it silently desyncs
        # alembic_version from the real schema (this bit a real deploy:
        # a later `alembic upgrade head` saw an old revision and crashed
        # trying to recreate tables create_all() had already made).
        print(
            "production DATABASE_URL detected -- refusing to run create_all(). "
            "Use `alembic upgrade head` instead.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    await init_db()
    print("Database initialised.")


if __name__ == "__main__":
    asyncio.run(main())
