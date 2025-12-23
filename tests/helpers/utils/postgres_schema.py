from __future__ import annotations

import asyncio

from infra.database.postgres_client import close_postgres_pool, init_postgres_pool
from infra.database.postgres_schema import ensure_schema  # reuse основной код


async def _main() -> None:
    pool = await init_postgres_pool(min_size=1, max_size=2)
    await ensure_schema(pool=pool)
    await close_postgres_pool()


if __name__ == "__main__":
    asyncio.run(_main())
