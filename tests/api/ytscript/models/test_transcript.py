from ytscript.models.segment import Segment
from ytscript.models.transcript import TranscriptDetails, TranscriptTrack


def test_segment_duration_defaults_to_zero():
    assert Segment(1.0, "a").duration == 0.0
    assert Segment(1.0, "a", 2.5).duration == 2.5


def test_transcript_track_fields():
    track = TranscriptTrack("pt", "Portuguese (auto-generated)", True, (("en", "English"),))
    assert track.language_code == "pt"
    assert track.is_generated is True
    assert track.translation_languages == (("en", "English"),)


def test_transcript_details_fields():
    details = TranscriptDetails(
        video=None,
        segments=[Segment(0, "a", 1)],
        language_code="pt",
        is_generated=True,
        translated_to=None,
        tracks=[],
    )
    assert details.video is None
    assert details.segments == [Segment(0, "a", 1)]
    assert details.translated_to is None
