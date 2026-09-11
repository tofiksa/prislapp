"""Testhjelper: holder en PostgreSQL advisory lock til den får en linje på stdin.

Brukes av låsetestene for å simulere en migrering som allerede er i gang.
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def hold(url: str, lock_id: int) -> None:
    engine = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": lock_id})
            print("locked", flush=True)
            sys.stdin.readline()
            await conn.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(hold(os.environ["DATABASE_URL"], int(sys.argv[1])))
