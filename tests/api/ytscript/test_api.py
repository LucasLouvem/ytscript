from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from infra.errors import (
    InvalidUrlError,
    LanguageNotAvailableError,
    NetworkError,
    TranscriptNotFoundError,
    TranslationNotAvailableError,
    UnsupportedDomainError,
)
from ytscript.api import app
from ytscript.models.segment import Segment
from ytscript.models.transcript import TranscriptDetails, TranscriptTrack
from ytscript.models.video import VideoInfo
from ytscript.views.transcript_view import build_details_payload

URL = "https://youtu.be/dQw4w9WgXcQ"


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
