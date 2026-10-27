from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from youtube_transcript_api import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    NotTranslatable,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
    VideoUnavailable,
)

from infra import errors
from infra.youtube_client import RawTrack, RawTranscript, fetch_transcript

VIDEO_ID = "dQw4w9WgXcQ"


class FakeTranscript:
    def __init__(self, code, language, is_generated, snippets, translations=(("en", "English"),)):
        self.language_code = code
        self.language = language
        self.is_generated = is_generated
        self.translation_languages = [
            SimpleNamespace(language_code=c, language=n) for c, n in translations
        ]
        self.is_translatable = bool(translations)
        self._snippets = snippets
        self.translated_to = None

    def fetch(self):
        snippets = [SimpleNamespace(start=s, text=t, duration=d) for s, t, d in self._snippets]
        return SimpleNamespace(
            snippets=snippets,
            language_code=self.translated_to or self.language_code,
            is_generated=self.is_generated,
        )

    def translate(self, code):
        self.translated_to = code
        return self


class FakeTranscriptList:
    def __init__(self, *transcripts):
        self.transcripts = transcripts

    def __iter__(self):
        return iter(self.transcripts)

    def _find(self, codes, generated):
        for code in codes:
            for transcript in self.transcripts:
                if transcript.language_code == code and transcript.is_generated == generated:
                    return transcript
        raise NoTranscriptFound(VIDEO_ID, list(codes), None)

    def find_manually_created_transcript(self, codes):
        return self._find(codes, generated=False)

    def find_generated_transcript(self, codes):
        return self._find(codes, generated=True)


def manual(code, text, translations=(("en", "English"),)):
    return FakeTranscript(code, f"{code} manual", False, [(0.0, text, 1.0)], translations)


def auto(code, text, translations=(("en", "English"),)):
    return FakeTranscript(code, f"{code} auto", True, [(0.0, text, 1.0)], translations)


@pytest.fixture
def api():
    with patch("infra.youtube_client.YouTubeTranscriptApi") as api_class:
        yield api_class.return_value


def serve(api, *transcripts):
    api.list.return_value = FakeTranscriptList(*transcripts)


def texts(result):
    return [text for _, text, _ in result.snippets]


def test_returns_snippets_in_source_order_with_duration(api):
    serve(
        api,
        FakeTranscript("pt", "pt manual", False, [(1.5, "a", 2.0), (3.0, "b", 1.0)]),
    )
    result = fetch_transcript(VIDEO_ID)
    assert result.snippets == [(1.5, "a", 2.0), (3.0, "b", 1.0)]
    assert result.language_code == "pt"
    assert result.is_generated is False
    assert result.translated_to is None
    api.list.assert_called_once_with(VIDEO_ID)


def test_default_prefers_manual_pt_br_over_everything(api):
    serve(api, auto("pt-BR", "auto-br"), manual("pt", "manual-pt"), manual("pt-BR", "manual-br"))
    assert texts(fetch_transcript(VIDEO_ID)) == ["manual-br"]


def test_default_prefers_manual_pt_over_generated(api):
    serve(api, auto("pt-BR", "auto-br"), manual("pt", "manual-pt"))
    assert texts(fetch_transcript(VIDEO_ID)) == ["manual-pt"]


def test_default_falls_back_to_generated_portuguese(api):
    serve(api, manual("en", "english"), auto("pt", "auto-pt"))
    result = fetch_transcript(VIDEO_ID)
    assert texts(result) == ["auto-pt"]
    assert result.is_generated is True


def test_default_without_portuguese_raises_transcript_not_found(api):
    serve(api, manual("en", "english"))
    with pytest.raises(errors.TranscriptNotFoundError) as exc_info:
        fetch_transcript(VIDEO_ID)
    assert exc_info.value.to_dict() == errors.TranscriptNotFoundError().to_dict()


def test_explicit_language_prefers_manual_then_generated(api):
    serve(api, auto("en", "auto-en"), manual("en", "manual-en"), manual("pt", "manual-pt"))
    assert texts(fetch_transcript(VIDEO_ID, language="en")) == ["manual-en"]


def test_explicit_language_uses_generated_when_no_manual(api):
    serve(api, auto("en", "auto-en"))
    result = fetch_transcript(VIDEO_ID, language="en")
    assert texts(result) == ["auto-en"]
    assert result.language_code == "en"


def test_explicit_language_missing_raises_language_not_available(api):
    serve(api, manual("pt", "manual-pt"))
    with pytest.raises(errors.LanguageNotAvailableError) as exc_info:
        fetch_transcript(VIDEO_ID, language="fr")
    assert exc_info.value.to_dict() == errors.LanguageNotAvailableError().to_dict()


def test_lists_all_tracks_with_translation_languages(api):
    serve(
        api,
        manual("pt", "a", translations=(("en", "English"), ("es", "Spanish"))),
        auto("en", "b", translations=()),
    )
    assert fetch_transcript(VIDEO_ID).tracks == [
        RawTrack("pt", "pt manual", False, (("en", "English"), ("es", "Spanish"))),
        RawTrack("en", "en auto", True, ()),
    ]


def test_translation_returns_translated_snippets_and_target(api):
    serve(api, auto("pt", "olá"))
    result = fetch_transcript(VIDEO_ID, translate_to="en")
    assert result.translated_to == "en"
    assert result.language_code == "pt"


def test_translation_to_unlisted_language_raises(api):
    serve(api, auto("pt", "olá", translations=(("en", "English"),)))
    with pytest.raises(errors.TranslationNotAvailableError) as exc_info:
        fetch_transcript(VIDEO_ID, translate_to="ja")
    assert exc_info.value.to_dict() == errors.TranslationNotAvailableError().to_dict()


def test_translation_of_untranslatable_track_raises(api):
    serve(api, auto("pt", "olá", translations=()))
    with pytest.raises(errors.TranslationNotAvailableError):
        fetch_transcript(VIDEO_ID, translate_to="en")


@pytest.mark.parametrize(
    ("library_error", "expected"),
    [
        (TranscriptsDisabled(VIDEO_ID), errors.TranscriptsDisabledError),
        (VideoUnavailable(VIDEO_ID), errors.VideoUnavailableError),
        (AgeRestricted(VIDEO_ID), errors.VideoUnavailableError),
        (IpBlocked(VIDEO_ID), errors.AccessBlockedError),
        (CouldNotRetrieveTranscript(VIDEO_ID), errors.TranscriptRetrievalError),
        (NotTranslatable(VIDEO_ID), errors.TranslationNotAvailableError),
        (TranslationLanguageNotAvailable(VIDEO_ID), errors.TranslationNotAvailableError),
        (requests.ConnectionError("sem rede"), errors.NetworkError),
    ],
)
def test_maps_library_errors(api, library_error, expected):
    api.list.side_effect = library_error
    with pytest.raises(expected) as exc_info:
        fetch_transcript(VIDEO_ID)
    assert exc_info.value.to_dict() == expected().to_dict()


def test_raw_transcript_is_a_named_tuple():
    result = RawTranscript([], "pt", True, None, [])
    assert result.language_code == "pt"
