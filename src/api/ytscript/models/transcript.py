from typing import NamedTuple

from ytscript.models.segment import Segment
from ytscript.models.video import VideoInfo


class TranscriptTrack(NamedTuple):
    language_code: str
    language: str
    is_generated: bool
    translation_languages: tuple[tuple[str, str], ...]


class TranscriptDetails(NamedTuple):
    video: VideoInfo | None
    segments: list[Segment]
    language_code: str
    is_generated: bool
    translated_to: str | None
    tracks: list[TranscriptTrack]
