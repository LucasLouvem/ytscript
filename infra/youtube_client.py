from typing import NamedTuple

import requests
from youtube_transcript_api import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    NotTranslatable,
    RequestBlocked,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
)

from infra.errors import (
    AccessBlockedError,
    LanguageNotAvailableError,
    NetworkError,
    TranscriptNotFoundError,
    TranscriptRetrievalError,
    TranscriptsDisabledError,
    TranslationNotAvailableError,
    VideoUnavailableError,
)

DEFAULT_LANGUAGES = ["pt-BR", "pt"]


class RawTrack(NamedTuple):
    language_code: str
    language: str
    is_generated: bool
    translation_languages: tuple[tuple[str, str], ...]


class RawTranscript(NamedTuple):
    snippets: list[tuple[float, str, float]]
    language_code: str
    is_generated: bool
    translated_to: str | None
    tracks: list[RawTrack]


def _select_transcript(transcripts, language: str | None):
    codes = [language] if language else DEFAULT_LANGUAGES
    try:
        try:
            return transcripts.find_manually_created_transcript(codes)
        except NoTranscriptFound:
            return transcripts.find_generated_transcript(codes)
    except NoTranscriptFound as error:
        not_found = LanguageNotAvailableError if language else TranscriptNotFoundError
        raise not_found() from error


def _translate(transcript, target: str):
    available = {item.language_code for item in transcript.translation_languages}
    if not transcript.is_translatable or target not in available:
        raise TranslationNotAvailableError()
    return transcript.translate(target)


def _track(transcript) -> RawTrack:
    translations = tuple(
        (item.language_code, item.language) for item in transcript.translation_languages
    )
    return RawTrack(
        transcript.language_code, transcript.language, transcript.is_generated, translations
    )


def fetch_transcript(
    video_id: str, language: str | None = None, translate_to: str | None = None
) -> RawTranscript:
    try:
        transcripts = YouTubeTranscriptApi().list(video_id)
        tracks = [_track(transcript) for transcript in transcripts]
        selected = _select_transcript(transcripts, language)
        source = _translate(selected, translate_to) if translate_to else selected
        fetched = source.fetch()
    except TranscriptsDisabled as error:
        raise TranscriptsDisabledError() from error
    except (VideoUnavailable, VideoUnplayable, AgeRestricted) as error:
        raise VideoUnavailableError() from error
    except RequestBlocked as error:
        raise AccessBlockedError() from error
    except (NotTranslatable, TranslationLanguageNotAvailable) as error:
        raise TranslationNotAvailableError() from error
    except CouldNotRetrieveTranscript as error:
        raise TranscriptRetrievalError() from error
    except requests.RequestException as error:
        raise NetworkError() from error

    snippets = [(item.start, item.text, item.duration) for item in fetched.snippets]
    return RawTranscript(
        snippets, selected.language_code, selected.is_generated, translate_to, tracks
    )
