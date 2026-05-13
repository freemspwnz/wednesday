"""Shared helpers for Redis cache repositories."""

from __future__ import annotations

from datetime import timedelta

from app.protocols import CacheClient, Logger


def raw_to_text(raw: object) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def ttl_to_seconds(ttl: int | timedelta | None) -> int | None:
    if ttl is None:
        return None
    if isinstance(ttl, timedelta):
        return int(ttl.total_seconds())
    return ttl


async def log_warning_and_invalidate_cache_key(
    *,
    client: CacheClient,
    logger: Logger,
    key: str,
    message: str,
    exc_info: bool = False,
) -> None:
    """Log a cache integrity issue (structured ``key``), then delete the key."""
    logger.warning(message, key=key, exc_info=exc_info)
    await client.delete(key)
