import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from infra.errors import VideoMetadataError
from infra.youtube_metadata import fetch_video_metadata, parse_player_response

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def page_with(player_response: dict) -> str:
    payload = json.dumps(player_response, ensure_ascii=False)
    return f"<html><script>var ytInitialPlayerResponse = {payload};var other = 1;</script></html>"


def load_page(video_id: str) -> str:
    data = json.loads((FIXTURES / f"player_response_{video_id}.json").read_text(encoding="utf-8"))
    return page_with(data)


def test_parse_video_with_single_asr_track():
    assert parse_player_response(load_page("xmK_BsRR9mk")) == {
        "video_id": "xmK_BsRR9mk",
        "title": "Meu plano pra ganhar US$ 6 mil como DEV SÊNIOR em 2026",
        "channel": "Yudi Ganeko",
        "duration_seconds": 1349,
        "view_count": 7697,
        "published_at": "2026-10-27T08:00:22-07:00",
        "thumbnail_url": "https://i.ytimg.com/vi/xmK_BsRR9mk/maxresdefault.jpg",
        "native_language": "pt",
    }


def test_parse_video_with_dubbed_audio_uses_default_audio_track():
    metadata = parse_player_response(load_page("lq76z9JvuVI"))
    assert metadata["title"].startswith("Brasil Soberano")
    assert metadata["channel"] == "Secretaria-Geral da Presidência da República"
    assert metadata["duration_seconds"] == 279
    assert metadata["view_count"] == 564609
    assert metadata["native_language"] == "pt-BR"


def minimal_response(**captions) -> dict:
    response = {
        "videoDetails": {
            "videoId": "abcdefghijk",
            "title": "t",
            "author": "a",
            "lengthSeconds": "10",
            "viewCount": "3",
        },
        "microformat": {"playerMicroformatRenderer": {"publishDate": "2026-01-01"}},
    }
    if captions:
        response["captions"] = {"playerCaptionsTracklistRenderer": captions}
    return response


def test_native_language_is_none_without_captions():
    assert parse_player_response(page_with(minimal_response()))["native_language"] is None


def test_native_language_falls_back_to_asr_track():
    response = minimal_response(captionTracks=[{"languageCode": "en", "kind": "asr"}])
    assert parse_player_response(page_with(response))["native_language"] == "en"


def test_native_language_ignores_manual_tracks_without_audio_info():
    response = minimal_response(captionTracks=[{"languageCode": "en"}])
    assert parse_player_response(page_with(response))["native_language"] is None


@pytest.mark.parametrize(
    "html",
    [
        "<html>sem dados</html>",
        "<script>var ytInitialPlayerResponse = {nao e json};</script>",
        page_with({"videoDetails": {}}),
        page_with({"playabilityStatus": {"status": "ERROR"}}),
    ],
)
def test_parse_invalid_page_raises_metadata_error(html):
    with pytest.raises(VideoMetadataError) as exc_info:
        parse_player_response(html)
    assert exc_info.value.to_dict() == VideoMetadataError().to_dict()


def test_fetch_video_metadata_requests_watch_page_for_the_video_id():
    response = MagicMock(text=load_page("xmK_BsRR9mk"))
    with patch("infra.youtube_metadata.requests.get", return_value=response) as get:
        metadata = fetch_video_metadata("xmK_BsRR9mk")

    assert metadata["title"].startswith("Meu plano")
    assert get.call_args.args[0] == "https://www.youtube.com/watch?v=xmK_BsRR9mk"
    assert get.call_args.kwargs["timeout"] > 0


@pytest.mark.parametrize(
    "failure",
    [requests.ConnectionError("sem rede"), requests.HTTPError("500")],
)
def test_fetch_video_metadata_network_failure_raises_metadata_error(failure):
    response = MagicMock()
    response.raise_for_status.side_effect = failure
    with patch("infra.youtube_metadata.requests.get", return_value=response):
        with pytest.raises(VideoMetadataError):
            fetch_video_metadata("xmK_BsRR9mk")

    with patch("infra.youtube_metadata.requests.get", side_effect=failure):
        with pytest.raises(VideoMetadataError):
            fetch_video_metadata("xmK_BsRR9mk")
