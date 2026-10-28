import math
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from infra.errors import (
    DailyLimitExceededError,
    GlobalLimitExceededError,
    RateLimitExceededError,
    YTScriptError,
)
from infra.redis_rate_limiter import RedisLimit, RedisRateLimiter

DEFAULT_LIMIT = 10
DEFAULT_WINDOW_SECONDS = 60.0
DEFAULT_DAILY_LIMIT = 100
DEFAULT_GLOBAL_DAILY_LIMIT = 2000
DEFAULT_KEY_LIMIT = 30
DEFAULT_KEY_DAILY_LIMIT = 1000
DEFAULT_KEY_GLOBAL_DAILY_LIMIT = 5000
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
        self._lock = threading.RLock()
        self._next_eviction = clock() + window_seconds

    def check(self, key: str) -> None:
        """Raises if `key` is over the limit; does not count a hit."""
        with self._lock:
            now = self._clock()
            hits = self._prune(key, now)
            if len(hits) >= self.limit:
                raise self._error_class(
                    retry_after=math.ceil(self.window_seconds - (now - hits[0]))
                )

    def hit(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(key, now).append(now)
            if len(self._hits) > EVICT_THRESHOLD and now >= self._next_eviction:
                self._evict_idle(now)

    def acquire(self, key: str) -> None:
        """Atomic `check` followed by `hit`."""
        with self._lock:
            self.check(key)
            self.hit(key)

    def reset(self) -> None:
        with self._lock:
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
    """Applies the global daily (when set), per-client daily and per-client minute limits.

    A blocked request counts for none of them.
    """

    def __init__(
        self,
        minute: SlidingWindowRateLimiter,
        daily: SlidingWindowRateLimiter,
        global_daily: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self.minute = minute
        self.daily = daily
        self.global_daily = global_daily
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            if self.global_daily:
                self.global_daily.check(GLOBAL_KEY)
            self.daily.check(key)
            self.minute.check(key)
            if self.global_daily:
                self.global_daily.hit(GLOBAL_KEY)
            self.daily.hit(key)
            self.minute.hit(key)

    def reset(self) -> None:
        with self._lock:
            self.minute.reset()
            self.daily.reset()
            if self.global_daily:
                self.global_daily.reset()


def memory_limiter_from_env() -> RateLimiter:
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


def memory_key_limiter_from_env() -> RateLimiter:
    return RateLimiter(
        minute=SlidingWindowRateLimiter(
            limit=int(os.environ.get("YTSCRIPT_KEY_RATE_LIMIT", DEFAULT_KEY_LIMIT)),
            window_seconds=float(os.environ.get("YTSCRIPT_RATE_WINDOW", DEFAULT_WINDOW_SECONDS)),
        ),
        daily=SlidingWindowRateLimiter(
            limit=int(os.environ.get("YTSCRIPT_KEY_DAILY_LIMIT", DEFAULT_KEY_DAILY_LIMIT)),
            window_seconds=DAY_SECONDS,
            error_class=DailyLimitExceededError,
        ),
        global_daily=SlidingWindowRateLimiter(
            limit=int(
                os.environ.get("YTSCRIPT_KEY_GLOBAL_DAILY_LIMIT", DEFAULT_KEY_GLOBAL_DAILY_LIMIT)
            ),
            window_seconds=DAY_SECONDS,
            error_class=GlobalLimitExceededError,
        ),
    )


def redis_credentials_from_env() -> tuple[str, str] | None:
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
    return (url, token) if url and token else None


def limiter_from_env() -> RateLimiter | RedisRateLimiter:
    credentials = redis_credentials_from_env()
    if credentials is None:
        return memory_limiter_from_env()
    url, token = credentials
    return RedisRateLimiter(
        url,
        token,
        limits=[
            RedisLimit(
                "global",
                int(os.environ.get("YTSCRIPT_GLOBAL_DAILY_LIMIT", DEFAULT_GLOBAL_DAILY_LIMIT)),
                DAY_SECONDS,
                GlobalLimitExceededError,
                per_client=False,
            ),
            RedisLimit(
                "daily",
                int(os.environ.get("YTSCRIPT_DAILY_LIMIT", DEFAULT_DAILY_LIMIT)),
                DAY_SECONDS,
                DailyLimitExceededError,
            ),
            RedisLimit(
                "minute",
                int(os.environ.get("YTSCRIPT_RATE_LIMIT", DEFAULT_LIMIT)),
                float(os.environ.get("YTSCRIPT_RATE_WINDOW", DEFAULT_WINDOW_SECONDS)),
                RateLimitExceededError,
            ),
        ],
    )


def key_limiter_from_env() -> RateLimiter | RedisRateLimiter:
    credentials = redis_credentials_from_env()
    if credentials is None:
        return memory_key_limiter_from_env()
    url, token = credentials
    return RedisRateLimiter(
        url,
        token,
        limits=[
            RedisLimit(
                "key-global",
                int(
                    os.environ.get(
                        "YTSCRIPT_KEY_GLOBAL_DAILY_LIMIT", DEFAULT_KEY_GLOBAL_DAILY_LIMIT
                    )
                ),
                DAY_SECONDS,
                GlobalLimitExceededError,
                per_client=False,
            ),
            RedisLimit(
                "key-daily",
                int(os.environ.get("YTSCRIPT_KEY_DAILY_LIMIT", DEFAULT_KEY_DAILY_LIMIT)),
                DAY_SECONDS,
                DailyLimitExceededError,
            ),
            RedisLimit(
                "key-minute",
                int(os.environ.get("YTSCRIPT_KEY_RATE_LIMIT", DEFAULT_KEY_LIMIT)),
                float(os.environ.get("YTSCRIPT_RATE_WINDOW", DEFAULT_WINDOW_SECONDS)),
                RateLimitExceededError,
            ),
        ],
    )
