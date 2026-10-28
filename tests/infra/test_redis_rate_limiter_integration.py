import os
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from infra.redis_rate_limiter import CHECK_AND_RECORD_SCRIPT

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1" or shutil.which("docker") is None,
        reason="defina RUN_INTEGRATION=1 e tenha Docker para rodar contra um Redis real",
    ),
]

DAY_MS = 86_400_000
LIMITS = [(2000, DAY_MS), (100, DAY_MS), (10, 60_000)]


@pytest.fixture(scope="module")
def redis_container():
    name = f"ytscript-redis-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "redis:7-alpine"],
        check=True,
        capture_output=True,
    )
    try:
        for _ in range(50):
            ping = subprocess.run(
                ["docker", "exec", name, "redis-cli", "ping"], capture_output=True, text=True
            )
            if ping.stdout.strip() == "PONG":
                break
            time.sleep(0.2)
        yield name
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True)


def redis_cli(container, *args):
    result = subprocess.run(
        ["docker", "exec", container, "redis-cli", *args], capture_output=True, text=True
    )
    return result.stdout.split()


def check(container, prefix, now_ms, limits=LIMITS):
    keys = [f"{prefix}:global", f"{prefix}:daily", f"{prefix}:minute"]
    args = [uuid.uuid4().hex, str(now_ms)]
    for limit, window in limits:
        args += [str(limit), str(window)]
    blocked, retry_after = redis_cli(container, "EVAL", CHECK_AND_RECORD_SCRIPT, "3", *keys, *args)
    return int(blocked), int(retry_after)


def test_allows_up_to_the_minute_limit_then_blocks_with_retry_after(redis_container):
    prefix = uuid.uuid4().hex
    for i in range(10):
        assert check(redis_container, prefix, 1000 + i) == (0, 0)
    blocked, retry_after = check(redis_container, prefix, 5000)
    assert blocked == 3
    assert retry_after == 56


def test_window_slides_and_frees_a_slot(redis_container):
    prefix = uuid.uuid4().hex
    limits = [(100, DAY_MS), (100, DAY_MS), (2, 60_000)]
    check(redis_container, prefix, 0, limits)
    check(redis_container, prefix, 30_000, limits)
    assert check(redis_container, prefix, 59_999, limits)[0] == 3
    assert check(redis_container, prefix, 60_000, limits) == (0, 0)
    assert check(redis_container, prefix, 60_001, limits)[0] == 3


def test_checks_global_then_daily_then_minute(redis_container):
    prefix = uuid.uuid4().hex
    limits = [(1, DAY_MS), (1, DAY_MS), (1, 60_000)]
    assert check(redis_container, prefix, 0, limits) == (0, 0)
    assert check(redis_container, prefix, 1, limits)[0] == 1


def test_blocked_request_is_not_recorded_in_any_limit(redis_container):
    prefix = uuid.uuid4().hex
    limits = [(100, DAY_MS), (100, DAY_MS), (1, 60_000)]
    check(redis_container, prefix, 0, limits)
    for i in range(5):
        assert check(redis_container, prefix, 1 + i, limits)[0] == 3
    assert redis_cli(redis_container, "ZCARD", f"{prefix}:global") == ["1"]
    assert redis_cli(redis_container, "ZCARD", f"{prefix}:daily") == ["1"]


def test_keys_expire_by_themselves(redis_container):
    prefix = uuid.uuid4().hex
    check(redis_container, prefix, int(time.time() * 1000))
    ttl = int(redis_cli(redis_container, "PTTL", f"{prefix}:minute")[0])
    assert 0 < ttl <= 60_000
    assert 0 < int(redis_cli(redis_container, "PTTL", f"{prefix}:global")[0]) <= DAY_MS


def test_parallel_requests_never_exceed_the_limit(redis_container):
    prefix = uuid.uuid4().hex
    now = int(time.time() * 1000)
    with ThreadPoolExecutor(max_workers=30) as pool:
        results = list(pool.map(lambda _: check(redis_container, prefix, now), range(30)))
    assert sum(1 for blocked, _ in results if blocked == 0) == 10
    assert redis_cli(redis_container, "ZCARD", f"{prefix}:minute") == ["10"]
