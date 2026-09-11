"""Ratebegrensning: Redis i produksjon når tilgjengelig, ellers in-process.

Tester bruker in-process med valgfri klokke. Redis kreves ikke for SQLite-tester.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from app.config import PRODUCTION_ENVIRONMENTS, settings

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(
        self,
        *,
        clock=time.monotonic,
        redis_url: str | None = None,
    ) -> None:
        self._clock = clock
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._redis_url = redis_url if redis_url is not None else settings.redis_url
        self._redis = None
        self._redis_failed = False
        self._warned = False

    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        if self._should_try_redis():
            allowed = await self._allow_redis(key, limit, window_seconds)
            if allowed is not None:
                return allowed
        return self._allow_memory(key, limit, window_seconds)

    def _should_try_redis(self) -> bool:
        env = (settings.environment or "").strip().lower()
        return (
            env in PRODUCTION_ENVIRONMENTS
            and bool(self._redis_url)
            and not self._redis_failed
        )

    async def _allow_redis(self, key: str, limit: int, window_seconds: int) -> bool | None:
        try:
            import redis.asyncio as redis

            if self._redis is None:
                self._redis = redis.from_url(
                    self._redis_url,
                    socket_connect_timeout=0.2,
                )
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, window_seconds)
            return int(count) <= limit
        except Exception:
            if not self._warned:
                logger.warning(
                    "Redis unavailable for rate limits; using in-process limiter"
                )
                self._warned = True
            self._redis_failed = True
            return None

    def _allow_memory(self, key: str, limit: int, window_seconds: int) -> bool:
        now = self._clock()
        window_start = now - window_seconds
        recent = [stamp for stamp in self._hits[key] if stamp > window_start]
        if len(recent) >= limit:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
