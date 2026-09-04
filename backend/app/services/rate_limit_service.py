"""A small fail-closed, tenant-principal rate limiter backed by Redis."""

from dataclasses import dataclass
from typing import Callable

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.exceptions import RateLimitExceededError, RateLimitUnavailableError


@dataclass(frozen=True)
class RateLimitDecision:
    limit: int
    used: int
    retry_after_seconds: int


class RateLimitService:
    """Atomically count a request in a fixed one-minute tenant-principal bucket."""

    _WINDOW_SECONDS = 60

    def __init__(
        self,
        *,
        redis_factory: Callable[[], Redis] | None = None,
        limit: int | None = None,
    ):
        self.redis_factory = redis_factory or self._create_client
        self.limit = limit if limit is not None else settings.RATE_LIMIT_REQUESTS_PER_MINUTE

    @staticmethod
    def _create_client() -> Redis:
        return Redis.from_url(settings.RATE_LIMIT_REDIS_URL, decode_responses=True)

    def enforce(self, *, tenant_id: int, principal: str) -> RateLimitDecision:
        if not isinstance(tenant_id, int) or tenant_id <= 0 or not principal:
            raise RateLimitUnavailableError()
        key = f"aegis:rate-limit:v1:{tenant_id}:{principal}"
        try:
            client = self.redis_factory()
            used = int(client.incr(key))
            if used == 1:
                client.expire(key, self._WINDOW_SECONDS)
            ttl = max(1, int(client.ttl(key)))
        except (RedisError, OSError, ValueError, TypeError) as error:
            raise RateLimitUnavailableError() from error
        if used > self.limit:
            raise RateLimitExceededError()
        return RateLimitDecision(limit=self.limit, used=used, retry_after_seconds=ttl)
