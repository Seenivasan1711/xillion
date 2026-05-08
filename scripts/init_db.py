#!/usr/bin/env python
"""Create the data directory and initialise the database."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    Path("data").mkdir(exist_ok=True)
    from xillion.db.session import init_db

    await init_db()
    print("Database initialised.")


if __name__ == "__main__":
    asyncio.run(main())
