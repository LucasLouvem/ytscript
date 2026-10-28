import math
import os
import time
from collections import defaultdict, deque
from collections.abc import Callable

from infra.errors import (
    DailyLimitExceededError,
    GlobalLimitExceededError,
    RateLimitExceededError,
    YTScriptError,
)

DEFAULT_LIMIT = 10
DEFAULT_WINDOW_SECONDS = 60.0
DEFAULT_DAILY_LIMIT = 100
DEFAULT_GLOBAL_DAILY_LIMIT = 2000
DAY_SECONDS = 86400.0
GLOBAL_KEY = "global"
EVICT_THRESHOLD = 1024


class SlidingWindowRateLimiter:
    """Allows at most `limit` hits per key within the last `window_seconds`."""

    def __init__(
        self,
        limit: int = DEFAULT_LIMIT,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        error_class: type[YTScriptError] = RateLimitExceededError,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._error_class = error_class
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._next_eviction = clock() + window_seconds

    def check(self, key: str) -> None:
        """Raises if `key` is over the limit; does not count a hit."""
        now = self._clock()
        hits = self._prune(key, now)
        if len(hits) >= self.limit:
            raise self._error_class(retry_after=math.ceil(self.window_seconds - (now - hits[0])))

    def hit(self, key: str) -> None:
        now = self._clock()
        self._prune(key, now).append(now)
        if len(self._hits) > EVICT_THRESHOLD and now >= self._next_eviction:
            self._evict_idle(now)

    def reset(self) -> None:
        self._hits.clear()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        return hits

    def _evict_idle(self, now: float) -> None:
        idle = [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window_seconds]
        for key in idle:
            del self._hits[key]
        self._next_eviction = now + self.window_seconds


class RateLimiter:
    """Applies the global daily, per-IP daily and per-IP minute limits.

    A blocked request counts for none of them.
    """

    def __init__(
        self,
        minute: SlidingWindowRateLimiter,
        daily: SlidingWindowRateLimiter,
        global_daily: SlidingWindowRateLimiter,
    ) -> None:
        self.minute = minute
        self.daily = daily
        self.global_daily = global_daily

    def check(self, key: str) -> None:
        self.global_daily.check(GLOBAL_KEY)
        self.daily.check(key)
        self.minute.check(key)
        self.global_daily.hit(GLOBAL_KEY)
        self.daily.hit(key)
        self.minute.hit(key)

    def reset(self) -> None:
        self.minute.reset()
        self.daily.reset()
        self.global_daily.reset()


def limiter_from_env() -> RateLimiter:
    return RateLimiter(
        minute=SlidingWindowRateLimiter(
            limit=int(os.environ.get("YTSCRIPT_RATE_LIMIT", DEFAULT_LIMIT)),
            window_seconds=float(os.environ.get("YTSCRIPT_RATE_WINDOW", DEFAULT_WINDOW_SECONDS)),
        ),
        daily=SlidingWindowRateLimiter(
            limit=int(os.environ.get("YTSCRIPT_DAILY_LIMIT", DEFAULT_DAILY_LIMIT)),
            window_seconds=DAY_SECONDS,
            error_class=DailyLimitExceededError,
        ),
        global_daily=SlidingWindowRateLimiter(
            limit=int(os.environ.get("YTSCRIPT_GLOBAL_DAILY_LIMIT", DEFAULT_GLOBAL_DAILY_LIMIT)),
            window_seconds=DAY_SECONDS,
            error_class=GlobalLimitExceededError,
        ),
    )
