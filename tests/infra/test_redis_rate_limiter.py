import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from infra.errors import DailyLimitExceededError, GlobalLimitExceededError, RateLimitExceededError
from infra.redis_rate_limiter import CHECK_AND_RECORD_SCRIPT, RedisLimit, RedisRateLimiter

URL = "https://example.upstash.io"
LIMITS = [
    RedisLimit("global", 2000, 86400, GlobalLimitExceededError, per_client=False),
    RedisLimit("daily", 100, 86400, DailyLimitExceededError),
    RedisLimit("minute", 10, 60, RateLimitExceededError),
]


def make_limiter(**kwargs):
    return RedisRateLimiter(URL, "secret", LIMITS, clock=lambda: 1000.0, **kwargs)


def reply(payload):
    return io.BytesIO(json.dumps(payload).encode())


def patch_urlopen(**kwargs):
    return patch("infra.redis_rate_limiter.urllib.request.urlopen", **kwargs)


def test_allows_request_and_sends_atomic_eval_with_all_limits():
    with patch_urlopen(return_value=reply({"result": [0, 0]})) as urlopen:
        make_limiter().check("1.2.3.4")

    request = urlopen.call_args.args[0]
    assert request.full_url == URL
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer secret"
    assert urlopen.call_args.kwargs["timeout"] == 2.0
    command = json.loads(request.data)
    assert command[:3] == ["EVAL", CHECK_AND_RECORD_SCRIPT, "3"]
    assert command[3:6] == [
        "ytscript:rl:global:all",
        "ytscript:rl:daily:1.2.3.4",
        "ytscript:rl:minute:1.2.3.4",
    ]
    member, now, *limits = command[6:]
    assert member.startswith("1000000:")
    assert now == "1000000"
    assert limits == ["2000", "86400000", "100", "86400000", "10", "60000"]


@pytest.mark.parametrize(
    "index, error_class",
    [(1, GlobalLimitExceededError), (2, DailyLimitExceededError), (3, RateLimitExceededError)],
)
def test_blocked_limit_raises_matching_error_with_retry_after(index, error_class):
    with patch_urlopen(return_value=reply({"result": [index, 42]})):
        with pytest.raises(error_class) as exc:
            make_limiter().check("1.2.3.4")

    assert exc.value.to_dict() == error_class().to_dict()
    assert exc.value.retry_after == 42


def test_retry_after_is_at_least_one_second():
    with patch_urlopen(return_value=reply({"result": [3, 0]})):
        with pytest.raises(RateLimitExceededError) as exc:
            make_limiter().check("a")
    assert exc.value.retry_after == 1


@pytest.mark.parametrize(
    "side_effect",
    [
        urllib.error.URLError("sem rede"),
        TimeoutError(),
        ConnectionResetError(),
    ],
)
def test_fails_open_when_redis_is_unreachable(side_effect, caplog):
    with patch_urlopen(side_effect=side_effect):
        make_limiter().check("a")
    assert "Rate limit indisponível" in caplog.text


def test_fails_open_on_redis_error_response(caplog):
    with patch_urlopen(return_value=reply({"error": "ERR boom"})):
        make_limiter().check("a")
    assert "ERR boom" in caplog.text


def test_fails_open_on_malformed_response():
    with patch_urlopen(return_value=io.BytesIO(b"<html>")):
        make_limiter().check("a")


def test_rejects_non_https_url():
    with pytest.raises(ValueError):
        RedisRateLimiter("http://example.upstash.io", "t", LIMITS)
    with pytest.raises(ValueError):
        RedisRateLimiter("file:///etc/passwd", "t", LIMITS)
