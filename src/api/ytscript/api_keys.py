import hashlib
import hmac
import logging
import os
from collections.abc import Iterable

from infra.errors import InvalidApiKeyError

KEY_ID_LENGTH = 16
MIN_KEY_LENGTH = 32

logger = logging.getLogger(__name__)


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class ApiKeys:
    """Known API keys, kept only as SHA-256 digests. Keys under 32 characters are ignored."""

    def __init__(self, keys: Iterable[str]) -> None:
        self._digests = set()
        for key in keys:
            if not key:
                continue
            if len(key) < MIN_KEY_LENGTH:
                logger.warning("Chave de API ignorada: menos de %d caracteres.", MIN_KEY_LENGTH)
                continue
            self._digests.add(_digest(key))

    def authenticate(self, provided: str | None) -> str | None:
        """Returns None without a key, a stable non-secret id for a valid one, or raises."""
        if provided is None:
            return None
        digest = _digest(provided)
        matched = False
        for known in self._digests:
            matched |= hmac.compare_digest(digest, known)
        if not matched:
            raise InvalidApiKeyError()
        return digest[:KEY_ID_LENGTH]


def api_keys_from_env() -> ApiKeys:
    raw = os.environ.get("YTSCRIPT_API_KEYS", "")
    return ApiKeys(part.strip() for part in raw.split(","))
