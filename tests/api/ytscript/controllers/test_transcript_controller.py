from unittest.mock import patch

import pytest

from infra.youtube_client import RawTrack, RawTranscript
from ytscript.controllers.transcript_controller import (
    extract_video_id,
    get_transcript,
    get_transcript_details,
)
from infra.errors import (
    EmptyTranscriptError,
    InvalidUrlError,
    InvalidVideoIdError,
    TranscriptNotFoundError,
    UnsupportedDomainError,
    VideoMetadataError,
)
from ytscript.models.segment import Segment
from ytscript.models.transcript import TranscriptTrack
from ytscript.models.video import VideoInfo

VIDEO_ID = "dQw4w9WgXcQ"
URL = f"https://youtu.be/{VIDEO_ID}"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42s&list=PL123",
        f"https://www.youtube.com/watch?feature=share&v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=abc",
        f"  https://youtu.be/{VIDEO_ID}  ",
    ],
)
def test_extract_video_id_valid(url):
    assert extract_video_id(url) == VIDEO_ID


@pytest.mark.parametrize(
    ("url", "expected_error"),
    [
        ("https://www.youtube.com/watch", InvalidVideoIdError),
        ("https://www.youtube.com/watch?v=", InvalidVideoIdError),
        ("https://www.youtube.com/watch?v=curto", InvalidVideoIdError),
        ("https://youtu.be/", InvalidVideoIdError),
        ("https://www.youtube.com/shorts/", InvalidVideoIdError),
        ("https://www.youtube.com/playlist?list=PL123", InvalidVideoIdError),
        (f"https://youtube.com.evil.com/watch?v={VIDEO_ID}", UnsupportedDomainError),
        (f"https://evil.com/watch?v={VIDEO_ID}", UnsupportedDomainError),
        (f"https://notyoutu.be/{VIDEO_ID}", UnsupportedDomainError),
        (f"https://user@evil.com/youtu.be/{VIDEO_ID}", UnsupportedDomainError),
        (f"http://www.youtube.com/watch?v={VIDEO_ID}", InvalidUrlError),
        (f"ftp://www.youtube.com/watch?v={VIDEO_ID}", InvalidUrlError),
        (VIDEO_ID, InvalidUrlError),
        ("isso não é uma url", InvalidUrlError),
        ("", InvalidUrlError),
        ("https://[::1/watch?v=" + VIDEO_ID, InvalidUrlError),
    ],
)
def test_extract_video_id_invalid(url, expected_error):
    with pytest.raises(expected_error) as exc_info:
        extract_video_id(url)
    assert exc_info.value.to_dict() == expected_error().to_dict()


CONTROLLER = "ytscript.controllers.transcript_controller"

RAW = RawTranscript(
    snippets=[(1.5, "a", 2.0), (3.0, "b", 1.0)],
    language_code="pt",
    is_generated=True,
    translated_to=None,
    tracks=[RawTrack("pt", "Portuguese (auto-generated)", True, (("en", "English"),))],
)
METADATA = {
    "video_id": VIDEO_ID,
    "title": "Título",
    "channel": "Canal",
    "duration_seconds": 1349,
    "view_count": 7671,
    "published_at": "2026-10-27T08:00:22-07:00",
    "thumbnail_url": f"https://i.ytimg.com/vi/{VIDEO_ID}/hqdefault.jpg",
    "native_language": "pt",
}


def test_get_transcript_returns_segments_for_valid_url():
    with patch(f"{CONTROLLER}.fetch_transcript", return_value=RAW) as fetch:
        segments = get_transcript(URL)

    assert segments == [Segment(1.5, "a", 2.0), Segment(3.0, "b", 1.0)]
    fetch.assert_called_once_with(VIDEO_ID)


def test_get_transcript_does_not_fetch_video_metadata():
    with (
        patch(f"{CONTROLLER}.fetch_transcript", return_value=RAW),
        patch(f"{CONTROLLER}.fetch_video_metadata") as metadata,
    ):
        get_transcript(URL)
    metadata.assert_not_called()


def test_get_transcript_rejects_invalid_url_without_fetching():
    with patch(f"{CONTROLLER}.fetch_transcript") as fetch:
        with pytest.raises(UnsupportedDomainError) as exc_info:
            get_transcript("https://evil.com/watch?v=" + VIDEO_ID)
        assert exc_info.value.to_dict() == UnsupportedDomainError().to_dict()
    fetch.assert_not_called()


@pytest.mark.parametrize("snippets", [[], [(0, "  ", 1.0), (1, "\n", 1.0)]])
def test_get_transcript_empty_raises(snippets):
    raw = RAW._replace(snippets=snippets)
    with patch(f"{CONTROLLER}.fetch_transcript", return_value=raw):
        with pytest.raises(EmptyTranscriptError) as exc_info:
            get_transcript(URL)
    assert exc_info.value.to_dict() == EmptyTranscriptError().to_dict()


def test_get_transcript_propagates_infra_errors():
    with patch(f"{CONTROLLER}.fetch_transcript", side_effect=TranscriptNotFoundError()):
        with pytest.raises(TranscriptNotFoundError) as exc_info:
            get_transcript(URL)
    assert exc_info.value.to_dict() == TranscriptNotFoundError().to_dict()


def test_get_transcript_details_combines_transcript_and_video():
    with (
        patch(f"{CONTROLLER}.fetch_transcript", return_value=RAW) as fetch,
        patch(f"{CONTROLLER}.fetch_video_metadata", return_value=METADATA) as metadata,
    ):
        details = get_transcript_details(URL, language="pt", translate_to="en")

    fetch.assert_called_once_with(VIDEO_ID, language="pt", translate_to="en")
    metadata.assert_called_once_with(VIDEO_ID)
    assert details.segments == [Segment(1.5, "a", 2.0), Segment(3.0, "b", 1.0)]
    assert details.language_code == "pt"
    assert details.is_generated is True
    assert details.translated_to is None
    assert details.tracks == [
        TranscriptTrack("pt", "Portuguese (auto-generated)", True, (("en", "English"),))
    ]
    assert details.video == VideoInfo(**METADATA)


def test_get_transcript_details_defaults_to_automatic_language():
    with (
        patch(f"{CONTROLLER}.fetch_transcript", return_value=RAW) as fetch,
        patch(f"{CONTROLLER}.fetch_video_metadata", return_value=METADATA),
    ):
        get_transcript_details(URL)
    fetch.assert_called_once_with(VIDEO_ID, language=None, translate_to=None)


def test_get_transcript_details_without_metadata_still_returns_transcript():
    with (
        patch(f"{CONTROLLER}.fetch_transcript", return_value=RAW),
        patch(f"{CONTROLLER}.fetch_video_metadata", side_effect=VideoMetadataError()),
    ):
        details = get_transcript_details(URL)
    assert details.video is None
    assert details.segments == [Segment(1.5, "a", 2.0), Segment(3.0, "b", 1.0)]


def test_get_transcript_details_rejects_invalid_url_without_any_request():
    with (
        patch(f"{CONTROLLER}.fetch_transcript") as fetch,
        patch(f"{CONTROLLER}.fetch_video_metadata") as metadata,
    ):
        with pytest.raises(InvalidUrlError):
            get_transcript_details("isso não é uma url")
    fetch.assert_not_called()
    metadata.assert_not_called()


def test_get_transcript_details_empty_transcript_raises():
    raw = RAW._replace(snippets=[])
    with (
        patch(f"{CONTROLLER}.fetch_transcript", return_value=raw),
        patch(f"{CONTROLLER}.fetch_video_metadata", return_value=METADATA),
    ):
        with pytest.raises(EmptyTranscriptError):
            get_transcript_details(URL)
