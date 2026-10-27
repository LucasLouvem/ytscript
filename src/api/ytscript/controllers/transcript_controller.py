import re
from urllib.parse import parse_qs, urlparse

from infra.errors import (
    EmptyTranscriptError,
    InvalidUrlError,
    InvalidVideoIdError,
    UnsupportedDomainError,
    VideoMetadataError,
)
from infra.youtube_client import RawTranscript, fetch_transcript
from infra.youtube_metadata import fetch_video_metadata
from ytscript.models.segment import Segment
from ytscript.models.transcript import TranscriptDetails, TranscriptTrack
from ytscript.models.video import VideoInfo

_VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")
_WATCH_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_SHORT_HOST = "youtu.be"


def extract_video_id(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        host = parsed.hostname
    except ValueError as error:
        raise InvalidUrlError() from error

    if parsed.scheme != "https" or host is None:
        raise InvalidUrlError()

    candidate: str | None = None
    if host in _WATCH_HOSTS:
        if parsed.path == "/watch":
            values = parse_qs(parsed.query).get("v")
            candidate = values[0] if values else None
        elif parsed.path.startswith("/shorts/"):
            candidate = parsed.path.removeprefix("/shorts/").split("/")[0]
    elif host == _SHORT_HOST:
        candidate = parsed.path.removeprefix("/").split("/")[0]
    else:
        raise UnsupportedDomainError()

    if not candidate or not _VIDEO_ID_PATTERN.fullmatch(candidate):
        raise InvalidVideoIdError()
    return candidate


def _segments_from(raw: RawTranscript) -> list[Segment]:
    segments = [Segment(start, text, duration) for start, text, duration in raw.snippets]
    if not any(segment.text.strip() for segment in segments):
        raise EmptyTranscriptError()
    return segments


def get_transcript(url: str) -> list[Segment]:
    return _segments_from(fetch_transcript(extract_video_id(url)))


def get_transcript_details(
    url: str, language: str | None = None, translate_to: str | None = None
) -> TranscriptDetails:
    video_id = extract_video_id(url)
    raw = fetch_transcript(video_id, language=language, translate_to=translate_to)
    segments = _segments_from(raw)
    try:
        video = VideoInfo(**fetch_video_metadata(video_id))
    except VideoMetadataError:
        video = None
    return TranscriptDetails(
        video=video,
        segments=segments,
        language_code=raw.language_code,
        is_generated=raw.is_generated,
        translated_to=raw.translated_to,
        tracks=[TranscriptTrack(*track) for track in raw.tracks],
    )
