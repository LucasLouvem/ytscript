import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from infra.errors import (
    InvalidUrlError,
    LanguageNotAvailableError,
    NetworkError,
    DailyLimitExceededError,
    GlobalLimitExceededError,
    InvalidApiKeyError,
    RateLimitExceededError,
    TranscriptNotFoundError,
    TranslationNotAvailableError,
    UnsupportedDomainError,
)
from ytscript.api import app, client_key
from ytscript.api_keys import ApiKeys
from ytscript.rate_limiter import memory_key_limiter_from_env, memory_limiter_from_env
from ytscript.models.segment import Segment
from ytscript.models.transcript import TranscriptDetails, TranscriptTrack
from ytscript.models.video import VideoInfo
from ytscript.views.transcript_view import build_details_payload

URL = "https://youtu.be/dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def rate_limiter(monkeypatch):
    limiter = memory_limiter_from_env()
    monkeypatch.setattr("ytscript.api.rate_limiter", limiter)
    return limiter


KEY = "a" * 40
OTHER_KEY = "b" * 40


@pytest.fixture(autouse=True)
def key_rate_limiter(monkeypatch):
    limiter = memory_key_limiter_from_env()
    monkeypatch.setattr("ytscript.api.key_rate_limiter", limiter)
    monkeypatch.setattr("ytscript.api.api_keys", ApiKeys([KEY, OTHER_KEY]))
    return limiter


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


VIDEO = VideoInfo(
    video_id="dQw4w9WgXcQ",
    title="Título",
    channel="Canal",
    duration_seconds=1349,
    view_count=7671,
    published_at="2026-10-27T08:00:22-07:00",
    thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    native_language="pt",
)
DETAILS = TranscriptDetails(
    video=VIDEO,
    segments=[Segment(12.7, "Olá", 2.0), Segment(65, "mundo", 1.0)],
    language_code="pt",
    is_generated=True,
    translated_to=None,
    tracks=[TranscriptTrack("pt", "Portuguese (auto-generated)", True, (("en", "English"),))],
)


def test_create_transcript_success_returns_video_transcript_and_formats(client):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS) as get:
        response = client.post("/api/transcripts", json={"url": URL})

    assert response.status_code == 200
    get.assert_called_once_with(URL, language=None, translate_to=None)
    body = response.json()
    assert body == build_details_payload(DETAILS)
    assert body["video"]["title"] == "Título"
    assert body["video"]["duration_seconds"] == 1349
    assert body["transcript"] == {
        "language_code": "pt",
        "is_generated": True,
        "translated_to": None,
    }
    assert body["tracks"][0]["translation_languages"] == [
        {"language_code": "en", "language": "English"}
    ]
    assert body["text"] == "[00:00:12] Olá\n\n[00:01:05] mundo"
    assert body["srt"].startswith("1\n00:00:12,700 --> 00:00:14,700\nOlá\n")
    assert body["markdown"].startswith("# Título\n\n- **Canal:** Canal\n")
    assert "**[00:00:12]** Olá\n\n**[00:01:05]** mundo\n" in body["markdown"]


def test_create_transcript_passes_language_and_translation(client):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS) as get:
        response = client.post(
            "/api/transcripts", json={"url": URL, "language": "pt", "translate_to": "en"}
        )

    assert response.status_code == 200
    get.assert_called_once_with(URL, language="pt", translate_to="en")


def test_create_transcript_without_video_metadata_returns_null_video(client):
    details = DETAILS._replace(video=None)
    with patch("ytscript.api.get_transcript_details", return_value=details):
        response = client.post("/api/transcripts", json={"url": URL})

    assert response.status_code == 200
    assert response.json()["video"] is None
    assert response.json()["segments"]
    assert response.json()["markdown"].startswith("# Transcrição\n")


@pytest.mark.parametrize(
    "error_class",
    [
        InvalidUrlError,
        UnsupportedDomainError,
        TranscriptNotFoundError,
        LanguageNotAvailableError,
        TranslationNotAvailableError,
        NetworkError,
    ],
)
def test_known_errors_return_exact_body_and_status(client, error_class):
    with patch("ytscript.api.get_transcript_details", side_effect=error_class()):
        response = client.post("/api/transcripts", json={"url": URL})

    expected = error_class()
    assert response.status_code == expected.status_code
    assert response.json() == expected.to_dict()


def test_invalid_domain_end_to_end(client):
    response = client.post("/api/transcripts", json={"url": "https://evil.com/watch?v=dQw4w9WgXcQ"})
    expected = UnsupportedDomainError()
    assert response.status_code == 400
    assert response.json() == expected.to_dict()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"url": 123},
        {"link": URL},
        {"url": URL, "language": 5},
        {"url": URL, "translate_to": []},
    ],
)
def test_invalid_request_body_returns_invalid_url_error(client, body):
    response = client.post("/api/transcripts", json=body)
    expected = InvalidUrlError()
    assert response.status_code == 400
    assert response.json() == expected.to_dict()


def test_serves_web_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "YTScript" in response.text


@pytest.mark.parametrize("path", ["/app.js", "/style.css"])
def test_serves_static_assets(client, path):
    assert client.get(path).status_code == 200


def test_unknown_api_route_is_not_found(client):
    assert client.get("/api/inexistente").status_code == 404


def test_create_transcript_is_rate_limited_per_client(client, rate_limiter):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        for _ in range(rate_limiter.minute.limit):
            assert client.post("/api/transcripts", json={"url": URL}).status_code == 200
        response = client.post("/api/transcripts", json={"url": URL})

    assert response.status_code == 429
    assert response.json() == RateLimitExceededError().to_dict()
    assert 1 <= int(response.headers["Retry-After"]) <= rate_limiter.minute.window_seconds


def test_health_is_not_rate_limited(client, rate_limiter):
    for _ in range(rate_limiter.minute.limit + 1):
        assert client.get("/api/health").status_code == 200


def test_create_transcript_is_blocked_by_daily_limit(client, rate_limiter, monkeypatch):
    monkeypatch.setattr(rate_limiter.daily, "limit", 2)
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        for _ in range(2):
            assert client.post("/api/transcripts", json={"url": URL}).status_code == 200
        response = client.post("/api/transcripts", json={"url": URL})

    assert response.status_code == 429
    assert response.json() == DailyLimitExceededError().to_dict()
    assert int(response.headers["Retry-After"]) > 0


def test_create_transcript_is_blocked_by_global_limit(client, rate_limiter, monkeypatch):
    monkeypatch.setattr(rate_limiter.global_daily, "limit", 1)
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        assert client.post("/api/transcripts", json={"url": URL}).status_code == 200
        response = client.post("/api/transcripts", json={"url": URL})

    assert response.status_code == 429
    assert response.json() == GlobalLimitExceededError().to_dict()
    assert int(response.headers["Retry-After"]) > 0


def make_request(headers=None, host="1.2.3.4"):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (host, 1234) if host else None,
    }
    return Request(scope)


def test_client_key_uses_socket_address_outside_vercel(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    request = make_request({"x-forwarded-for": "9.9.9.9"})
    assert client_key(request) == "1.2.3.4"


def test_client_key_uses_first_forwarded_address_on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    request = make_request({"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
    assert client_key(request) == "9.9.9.9"


def test_client_key_falls_back_to_socket_on_vercel_without_header(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert client_key(make_request()) == "1.2.3.4"


def test_client_key_without_any_address(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    assert client_key(make_request(host=None)) == "unknown"


def test_concurrent_posts_from_one_client_get_exactly_the_limit_through(rate_limiter):
    barrier = threading.Barrier(40)

    def post(_):
        barrier.wait()
        with TestClient(app) as local:
            return local.post("/api/transcripts", json={"url": URL}).status_code

    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        with ThreadPoolExecutor(max_workers=40) as pool:
            statuses = list(pool.map(post, range(40)))

    assert statuses.count(200) == rate_limiter.minute.limit
    assert statuses.count(429) == 40 - rate_limiter.minute.limit
    assert set(statuses) == {200, 429}


def test_blocked_requests_never_reach_the_transcript_controller(client, rate_limiter):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS) as get:
        for _ in range(rate_limiter.minute.limit + 15):
            client.post("/api/transcripts", json={"url": URL})
    assert get.call_count == rate_limiter.minute.limit


def post(client, key=None):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.post("/api/transcripts", json={"url": URL}, headers=headers)


def test_valid_key_uses_its_own_limits_not_the_public_ones(client, rate_limiter):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        for _ in range(rate_limiter.minute.limit + 5):
            assert post(client, KEY).status_code == 200
        assert post(client).status_code == 200


def test_valid_key_requests_do_not_consume_the_public_quota(client, rate_limiter):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        for _ in range(20):
            post(client, KEY)
        for _ in range(rate_limiter.minute.limit):
            assert post(client).status_code == 200
        assert post(client).status_code == 429


def test_key_is_limited_per_minute_with_retry_after(client, key_rate_limiter):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        for _ in range(key_rate_limiter.minute.limit):
            assert post(client, KEY).status_code == 200
        response = post(client, KEY)

    assert response.status_code == 429
    assert response.json() == RateLimitExceededError().to_dict()
    assert int(response.headers["Retry-After"]) > 0


def test_key_is_limited_per_day(client, key_rate_limiter, monkeypatch):
    monkeypatch.setattr(key_rate_limiter.daily, "limit", 2)
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        assert post(client, KEY).status_code == 200
        assert post(client, KEY).status_code == 200
        response = post(client, KEY)

    assert response.status_code == 429
    assert response.json() == DailyLimitExceededError().to_dict()


def test_keys_have_independent_limits(client, key_rate_limiter, monkeypatch):
    monkeypatch.setattr(key_rate_limiter.minute, "limit", 1)
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        assert post(client, KEY).status_code == 200
        assert post(client, KEY).status_code == 429
        assert post(client, OTHER_KEY).status_code == 200


def test_all_keys_together_are_capped_by_the_keys_global_limit(
    client, key_rate_limiter, monkeypatch
):
    monkeypatch.setattr(key_rate_limiter.global_daily, "limit", 2)
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        assert post(client, KEY).status_code == 200
        assert post(client, OTHER_KEY).status_code == 200
        response = post(client, KEY)

    assert response.status_code == 429
    assert response.json() == GlobalLimitExceededError().to_dict()


def test_unknown_key_gets_401_with_exact_body_and_never_reaches_the_controller(client):
    with patch("ytscript.api.get_transcript_details") as get:
        response = post(client, "c" * 40)

    assert response.status_code == 401
    assert response.json() == InvalidApiKeyError().to_dict()
    get.assert_not_called()


def test_key_header_is_rejected_when_the_server_has_no_keys(client, monkeypatch):
    monkeypatch.setattr("ytscript.api.api_keys", ApiKeys([]))
    assert post(client, KEY).status_code == 401


def test_invalid_key_does_not_fall_back_to_the_public_limits(client):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS) as get:
        assert post(client, "c" * 40).status_code == 401
        get.assert_not_called()


def test_invalid_key_attempts_count_against_the_public_ip_limit(client, rate_limiter):
    for _ in range(rate_limiter.minute.limit):
        assert post(client, "c" * 40).status_code == 401
    response = post(client, "c" * 40)

    assert response.status_code == 429
    assert response.json() == RateLimitExceededError().to_dict()


def test_blocked_key_request_never_reaches_the_controller(client, key_rate_limiter):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS) as get:
        for _ in range(key_rate_limiter.minute.limit + 10):
            post(client, KEY)
    assert get.call_count == key_rate_limiter.minute.limit


def test_raw_key_never_appears_in_limiter_state(client, key_rate_limiter):
    with patch("ytscript.api.get_transcript_details", return_value=DETAILS):
        post(client, KEY)
    assert KEY not in repr(key_rate_limiter.minute._hits)
    assert KEY not in repr(key_rate_limiter.daily._hits)
