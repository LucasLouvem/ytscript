import json
import logging
import time
import urllib.request
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from infra.errors import YTScriptError

logger = logging.getLogger(__name__)

KEY_PREFIX = "ytscript:rl"
REQUEST_TIMEOUT_SECONDS = 2.0

CHECK_AND_RECORD_SCRIPT = """
local now = tonumber(ARGV[2])
for i = 1, #KEYS do
  local limit = tonumber(ARGV[1 + i * 2])
  local window = tonumber(ARGV[2 + i * 2])
  redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', now - window)
  if redis.call('ZCARD', KEYS[i]) >= limit then
    local oldest = redis.call('ZRANGE', KEYS[i], 0, 0, 'WITHSCORES')
    return {i, math.ceil((tonumber(oldest[2]) + window - now) / 1000)}
  end
end
for i = 1, #KEYS do
  redis.call('ZADD', KEYS[i], now, ARGV[1])
  redis.call('PEXPIRE', KEYS[i], tonumber(ARGV[2 + i * 2]))
end
return {0, 0}
"""


@dataclass(frozen=True)
class RedisLimit:
    name: str
    limit: int
    window_seconds: float
    error_class: type[YTScriptError]
    per_client: bool = True


class RedisCommandError(ValueError):
    pass


class RedisRateLimiter:
    """Sliding-window limits kept in Upstash Redis (REST API), checked atomically by a Lua script.

    Limits are checked in order; a blocked request is not recorded in any of them. If Redis is
    unreachable the request is allowed (fail open) and the failure is logged.
    """

    def __init__(
        self,
        url: str,
        token: str,
        limits: Sequence[RedisLimit],
        clock: Callable[[], float] = time.time,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if not url.startswith("https://"):
            raise ValueError("A URL do Redis deve usar https.")
        self._url = url
        self._token = token
        self._limits = tuple(limits)
        self._clock = clock
        self._timeout = timeout

    def check(self, client_key: str) -> None:
        now_ms = int(self._clock() * 1000)
        keys = [self._key(limit, client_key) for limit in self._limits]
        args = [f"{now_ms}:{uuid.uuid4().hex}", str(now_ms)]
        for limit in self._limits:
            args += [str(limit.limit), str(int(limit.window_seconds * 1000))]
        try:
            blocked_index, retry_after = self._eval(keys, args)
        except (OSError, ValueError) as error:
            logger.warning("Rate limit indisponível, requisição liberada: %s", error)
            return
        if blocked_index:
            raise self._limits[blocked_index - 1].error_class(retry_after=max(1, retry_after))

    def _key(self, limit: RedisLimit, client_key: str) -> str:
        return f"{KEY_PREFIX}:{limit.name}:{client_key if limit.per_client else 'all'}"

    def _eval(self, keys: list[str], args: list[str]) -> tuple[int, int]:
        command = ["EVAL", CHECK_AND_RECORD_SCRIPT, str(len(keys)), *keys, *args]
        request = urllib.request.Request(
            self._url,
            data=json.dumps(command).encode(),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            body = json.load(response)
        if "error" in body:
            raise RedisCommandError(body["error"])
        blocked_index, retry_after = body["result"]
        return int(blocked_index), int(retry_after)
