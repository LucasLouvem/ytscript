import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from infra.errors import DailyLimitExceededError, GlobalLimitExceededError, RateLimitExceededError
from infra.redis_rate_limiter import RedisRateLimiter
from ytscript.rate_limiter import (
    RateLimiter,
    SlidingWindowRateLimiter,
    key_limiter_from_env,
    limiter_from_env,
    memory_key_limiter_from_env,
    memory_limiter_from_env,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make(limit=2, window=60.0):
    clock = FakeClock()
    return SlidingWindowRateLimiter(limit, window, clock), clock


def use(limiter, key):
    limiter.check(key)
    limiter.hit(key)


def test_allows_up_to_limit():
    limiter, _ = make(limit=2)
    use(limiter, "a")
    use(limiter, "a")


def test_blocks_over_limit_with_exact_body_and_retry_after():
    limiter, clock = make(limit=2, window=60)
    use(limiter, "a")
    clock.now = 10
    use(limiter, "a")
    clock.now = 20
    with pytest.raises(RateLimitExceededError) as exc:
        limiter.check("a")
    assert exc.value.to_dict() == RateLimitExceededError().to_dict()
    assert exc.value.retry_after == 40


def test_allows_again_after_window():
    limiter, clock = make(limit=1, window=60)
    use(limiter, "a")
    clock.now = 60
    use(limiter, "a")


def test_keys_are_independent():
    limiter, _ = make(limit=1)
    use(limiter, "a")
    use(limiter, "b")


def test_acquire_checks_and_counts():
    limiter, _ = make(limit=1)
    limiter.acquire("a")
    with pytest.raises(RateLimitExceededError):
        limiter.acquire("a")


def test_check_alone_does_not_count():
    limiter, _ = make(limit=1)
    limiter.check("a")
    limiter.check("a")


def test_idle_keys_are_evicted(monkeypatch):
    monkeypatch.setattr("ytscript.rate_limiter.EVICT_THRESHOLD", 2)
    limiter, clock = make(limit=1, window=60)
    for key in ("a", "b", "c"):
        use(limiter, key)
    clock.now = 61
    use(limiter, "d")
    assert set(limiter._hits) == {"d"}


def make_pair(minute_limit=2, daily_limit=3, global_limit=1000):
    clock = FakeClock()
    minute = SlidingWindowRateLimiter(minute_limit, 60, clock)
    daily = SlidingWindowRateLimiter(daily_limit, 86400, clock, DailyLimitExceededError)
    global_daily = SlidingWindowRateLimiter(global_limit, 86400, clock, GlobalLimitExceededError)
    return RateLimiter(minute, daily, global_daily), clock


def test_daily_limit_blocks_even_when_minute_window_is_free():
    limiter, clock = make_pair(minute_limit=2, daily_limit=3)
    for second in (0, 100, 200):
        clock.now = second
        limiter.check("a")
    clock.now = 300
    with pytest.raises(DailyLimitExceededError) as exc:
        limiter.check("a")
    assert exc.value.to_dict() == DailyLimitExceededError().to_dict()
    assert exc.value.retry_after == 86400 - 300


def test_daily_limit_resets_after_a_day():
    limiter, clock = make_pair(minute_limit=5, daily_limit=1)
    limiter.check("a")
    clock.now = 86400
    limiter.check("a")


def test_minute_limit_still_applies_before_daily():
    limiter, _ = make_pair(minute_limit=1, daily_limit=5)
    limiter.check("a")
    with pytest.raises(RateLimitExceededError):
        limiter.check("a")


def test_blocked_request_counts_for_neither_limit():
    limiter, clock = make_pair(minute_limit=1, daily_limit=2)
    limiter.check("a")
    for second in (10, 20):
        clock.now = second
        with pytest.raises(RateLimitExceededError):
            limiter.check("a")
    clock.now = 60
    limiter.check("a")
    clock.now = 120
    with pytest.raises(DailyLimitExceededError):
        limiter.check("a")


def test_global_limit_sums_all_keys_and_blocks_new_ones():
    limiter, clock = make_pair(minute_limit=5, daily_limit=5, global_limit=2)
    limiter.check("a")
    limiter.check("b")
    clock.now = 100
    with pytest.raises(GlobalLimitExceededError) as exc:
        limiter.check("c")
    assert exc.value.to_dict() == GlobalLimitExceededError().to_dict()
    assert exc.value.retry_after == 86400 - 100


def test_global_limit_resets_after_a_day():
    limiter, clock = make_pair(global_limit=1)
    limiter.check("a")
    clock.now = 86400
    limiter.check("b")


def test_request_blocked_per_ip_does_not_use_global_quota():
    limiter, clock = make_pair(minute_limit=1, global_limit=2)
    limiter.check("a")
    for second in (1, 2, 3):
        clock.now = second
        with pytest.raises(RateLimitExceededError):
            limiter.check("a")
    limiter.check("b")


def test_limiter_from_env(monkeypatch):
    monkeypatch.setenv("YTSCRIPT_RATE_LIMIT", "3")
    monkeypatch.setenv("YTSCRIPT_RATE_WINDOW", "5")
    monkeypatch.setenv("YTSCRIPT_DAILY_LIMIT", "7")
    monkeypatch.setenv("YTSCRIPT_GLOBAL_DAILY_LIMIT", "50")
    limiter = memory_limiter_from_env()
    assert (limiter.minute.limit, limiter.minute.window_seconds) == (3, 5.0)
    assert (limiter.daily.limit, limiter.daily.window_seconds) == (7, 86400.0)
    assert (limiter.global_daily.limit, limiter.global_daily.window_seconds) == (50, 86400.0)


def test_limiter_from_env_defaults(monkeypatch):
    for name in (
        "YTSCRIPT_RATE_LIMIT",
        "YTSCRIPT_RATE_WINDOW",
        "YTSCRIPT_DAILY_LIMIT",
        "YTSCRIPT_GLOBAL_DAILY_LIMIT",
    ):
        monkeypatch.delenv(name, raising=False)
    limiter = memory_limiter_from_env()
    assert (limiter.minute.limit, limiter.minute.window_seconds) == (10, 60.0)
    assert (limiter.daily.limit, limiter.daily.window_seconds) == (100, 86400.0)
    assert (limiter.global_daily.limit, limiter.global_daily.window_seconds) == (2000, 86400.0)


REDIS_ENV = (
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "KV_REST_API_URL",
    "KV_REST_API_TOKEN",
)


@pytest.fixture
def no_redis_env(monkeypatch):
    for name in REDIS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_limiter_from_env_uses_memory_without_redis_credentials(no_redis_env):
    assert isinstance(limiter_from_env(), RateLimiter)


def test_limiter_from_env_uses_redis_with_upstash_credentials(no_redis_env, monkeypatch):
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "token")
    limiter = limiter_from_env()
    assert isinstance(limiter, RedisRateLimiter)
    assert [(l.name, l.limit, l.per_client) for l in limiter._limits] == [
        ("global", 2000, False),
        ("daily", 100, True),
        ("minute", 10, True),
    ]


def test_limiter_from_env_accepts_vercel_kv_names(no_redis_env, monkeypatch):
    monkeypatch.setenv("KV_REST_API_URL", "https://example.upstash.io")
    monkeypatch.setenv("KV_REST_API_TOKEN", "token")
    assert isinstance(limiter_from_env(), RedisRateLimiter)


def test_limiter_from_env_needs_both_url_and_token(no_redis_env, monkeypatch):
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example.upstash.io")
    assert isinstance(limiter_from_env(), RateLimiter)


def slow_clock():
    time.sleep(0.0005)
    return time.monotonic()


def run_concurrently(calls, workers=50):
    barrier = threading.Barrier(workers)

    def attempt(call):
        barrier.wait()
        try:
            call()
            return True
        except RateLimitExceededError:
            return False

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(attempt, calls[:workers]))


def test_concurrent_requests_from_one_client_never_exceed_the_limit():
    limiter = SlidingWindowRateLimiter(10, 60, slow_clock)
    results = run_concurrently([lambda: limiter.acquire("a")] * 50)
    assert sum(results) == 10


def test_concurrent_combined_limiter_never_exceeds_any_limit():
    minute = SlidingWindowRateLimiter(10, 60, slow_clock)
    daily = SlidingWindowRateLimiter(100, 86400, slow_clock, DailyLimitExceededError)
    global_daily = SlidingWindowRateLimiter(20, 86400, slow_clock, GlobalLimitExceededError)
    limiter = RateLimiter(minute, daily, global_daily)

    def request():
        try:
            limiter.check("a")
            return True
        except (RateLimitExceededError, DailyLimitExceededError, GlobalLimitExceededError):
            return False

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: request(), range(50)))
    assert sum(results) == 10
    assert len(minute._hits["a"]) == 10


def test_concurrent_requests_from_different_clients_do_not_interfere():
    limiter = SlidingWindowRateLimiter(1, 60, slow_clock)
    results = run_concurrently([lambda key=f"ip{i}": limiter.acquire(key) for i in range(50)])
    assert all(results)


def test_many_clients_keep_active_counters_after_eviction(monkeypatch):
    monkeypatch.setattr("ytscript.rate_limiter.EVICT_THRESHOLD", 100)
    limiter, clock = make(limit=1, window=60)
    use(limiter, "active")
    clock.now = 30
    for i in range(500):
        use(limiter, f"ip{i}")
    clock.now = 61
    use(limiter, "trigger-eviction")
    clock.now = 62
    with pytest.raises(RateLimitExceededError):
        limiter.check("ip499")


def test_idle_clients_do_not_grow_memory_without_bound(monkeypatch):
    monkeypatch.setattr("ytscript.rate_limiter.EVICT_THRESHOLD", 100)
    limiter, clock = make(limit=1, window=60)
    for second in range(0, 600, 1):
        clock.now = second
        use(limiter, f"ip{second}")
    assert len(limiter._hits) < 300


def test_key_limits_are_strict_by_default(monkeypatch):
    for name in (
        "YTSCRIPT_KEY_RATE_LIMIT",
        "YTSCRIPT_KEY_DAILY_LIMIT",
        "YTSCRIPT_KEY_GLOBAL_DAILY_LIMIT",
        "YTSCRIPT_RATE_WINDOW",
    ):
        monkeypatch.delenv(name, raising=False)
    limiter = memory_key_limiter_from_env()
    assert limiter.minute.limit == 30
    assert limiter.daily.limit == 1000
    assert limiter.global_daily.limit == 5000


def test_key_limits_come_from_env(monkeypatch):
    monkeypatch.setenv("YTSCRIPT_KEY_RATE_LIMIT", "5")
    monkeypatch.setenv("YTSCRIPT_KEY_DAILY_LIMIT", "50")
    monkeypatch.setenv("YTSCRIPT_KEY_GLOBAL_DAILY_LIMIT", "70")
    limiter = memory_key_limiter_from_env()
    assert (limiter.minute.limit, limiter.daily.limit, limiter.global_daily.limit) == (5, 50, 70)


def test_key_limiter_uses_memory_without_redis_credentials(no_redis_env):
    assert isinstance(key_limiter_from_env(), RateLimiter)


def test_key_limiter_uses_redis_with_separate_key_namespaces(no_redis_env, monkeypatch):
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "token")
    monkeypatch.delenv("YTSCRIPT_KEY_RATE_LIMIT", raising=False)
    monkeypatch.delenv("YTSCRIPT_KEY_DAILY_LIMIT", raising=False)
    monkeypatch.delenv("YTSCRIPT_KEY_GLOBAL_DAILY_LIMIT", raising=False)
    public = {l.name for l in limiter_from_env()._limits}
    keyed = key_limiter_from_env()
    assert [(l.name, l.limit, l.per_client) for l in keyed._limits] == [
        ("key-global", 5000, False),
        ("key-daily", 1000, True),
        ("key-minute", 30, True),
    ]
    assert public.isdisjoint(l.name for l in keyed._limits)


def test_limiter_without_global_cap_still_limits_per_client():
    clock = FakeClock()
    limiter = RateLimiter(
        SlidingWindowRateLimiter(1, 60, clock),
        SlidingWindowRateLimiter(5, 86400, clock, DailyLimitExceededError),
    )
    limiter.check("a")
    with pytest.raises(RateLimitExceededError):
        limiter.check("a")
    limiter.check("b")
    limiter.reset()
    limiter.check("a")
