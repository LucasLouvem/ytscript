import pytest

from ytscript.models.segment import Segment
from ytscript.models.transcript import TranscriptDetails, TranscriptTrack
from ytscript.models.video import VideoInfo
from ytscript.views.transcript_view import (
    build_details_payload,
    build_transcript_payload,
    format_markdown,
    format_srt,
    format_srt_timestamp,
    format_timestamp,
    format_transcript,
)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (12, "00:00:12"),
        (59.9, "00:00:59"),
        (60, "00:01:00"),
        (3600, "01:00:00"),
        (3725, "01:02:05"),
        (36000.5, "10:00:00"),
        (12.999, "00:00:12"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


def test_format_transcript_preserves_order_and_text():
    segments = [
        Segment(12.4, "Antes de investir em uma empresa,\nprecisamos analisar seus fundamentos."),
        Segment(19.0, "O preço de uma ação não determina"),
    ]
    assert format_transcript(segments) == (
        "[00:00:12] Antes de investir em uma empresa,\n"
        "precisamos analisar seus fundamentos.\n"
        "\n"
        "[00:00:19] O preço de uma ação não determina"
    )


def test_format_transcript_does_not_reorder_segments():
    segments = [Segment(30, "b"), Segment(10, "a")]
    assert format_transcript(segments) == "[00:00:30] b\n\n[00:00:10] a"


def test_format_transcript_drops_blank_segments_and_blank_lines():
    segments = [Segment(1, "  \n "), Segment(2, "olá\n\n mundo ")]
    assert format_transcript(segments) == "[00:00:02] olá\nmundo"


def test_format_transcript_empty():
    assert format_transcript([]) == ""


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00,000"),
        (12.5, "00:00:12,500"),
        (59.9996, "00:01:00,000"),
        (3725.04, "01:02:05,040"),
    ],
)
def test_format_srt_timestamp(seconds, expected):
    assert format_srt_timestamp(seconds) == expected


def test_format_srt_uses_start_plus_duration():
    segments = [Segment(12.0, "Olá", 3.5), Segment(20.0, "mundo", 2.0)]
    assert format_srt(segments) == (
        "1\n00:00:12,000 --> 00:00:15,500\nOlá\n\n2\n00:00:20,000 --> 00:00:22,000\nmundo\n"
    )


def test_format_srt_clamps_end_to_next_start_when_overlapping():
    segments = [Segment(0.0, "a", 5.0), Segment(3.0, "b", 2.0)]
    assert format_srt(segments) == (
        "1\n00:00:00,000 --> 00:00:03,000\na\n\n2\n00:00:03,000 --> 00:00:05,000\nb\n"
    )


def test_format_srt_without_duration_ends_at_next_start_or_one_second_later():
    segments = [Segment(1.0, "a"), Segment(4.0, "b")]
    assert format_srt(segments) == (
        "1\n00:00:01,000 --> 00:00:04,000\na\n\n2\n00:00:04,000 --> 00:00:05,000\nb\n"
    )


def test_format_srt_skips_blank_segments_and_renumbers():
    segments = [Segment(0, "  ", 1), Segment(1, "ok", 1)]
    assert format_srt(segments) == "1\n00:00:01,000 --> 00:00:02,000\nok\n"


def test_format_srt_empty():
    assert format_srt([]) == ""


def test_build_transcript_payload():
    payload = build_transcript_payload([Segment(12.7, "Olá", 2.0), Segment(65, "mundo", 1.0)])
    assert payload == {
        "segments": [
            {"start": 12.7, "end": 14.7, "timestamp": "00:00:12", "text": "Olá"},
            {"start": 65, "end": 66.0, "timestamp": "00:01:05", "text": "mundo"},
        ],
        "text": "[00:00:12] Olá\n\n[00:01:05] mundo",
        "srt": format_srt([Segment(12.7, "Olá", 2.0), Segment(65, "mundo", 1.0)]),
    }


def test_build_transcript_payload_empty():
    assert build_transcript_payload([]) == {"segments": [], "text": "", "srt": ""}


VIDEO = VideoInfo(
    video_id="xmK_BsRR9mk",
    title="Título",
    channel="Canal",
    duration_seconds=1349,
    view_count=7671,
    published_at="2026-10-27T08:00:22-07:00",
    thumbnail_url="https://i.ytimg.com/vi/xmK_BsRR9mk/hqdefault.jpg",
    native_language="pt",
)
TRACK = TranscriptTrack("pt", "Portuguese (auto-generated)", True, (("en", "English"),))


def test_build_details_payload_with_video():
    details = TranscriptDetails(
        video=VIDEO,
        segments=[Segment(1, "a", 1)],
        language_code="pt",
        is_generated=True,
        translated_to=None,
        tracks=[TRACK],
    )
    payload = build_details_payload(details)
    assert payload["video"] == {
        "id": "xmK_BsRR9mk",
        "title": "Título",
        "channel": "Canal",
        "duration_seconds": 1349,
        "view_count": 7671,
        "published_at": "2026-10-27T08:00:22-07:00",
        "thumbnail_url": "https://i.ytimg.com/vi/xmK_BsRR9mk/hqdefault.jpg",
        "native_language": "pt",
    }
    assert payload["transcript"] == {
        "language_code": "pt",
        "is_generated": True,
        "translated_to": None,
    }
    assert payload["tracks"] == [
        {
            "language_code": "pt",
            "language": "Portuguese (auto-generated)",
            "is_generated": True,
            "translation_languages": [{"language_code": "en", "language": "English"}],
        }
    ]
    assert payload["segments"] == build_transcript_payload([Segment(1, "a", 1)])["segments"]
    assert payload["text"] == "[00:00:01] a"
    assert payload["srt"] == format_srt([Segment(1, "a", 1)])


def test_build_details_payload_without_video_has_null_video():
    details = TranscriptDetails(None, [Segment(1, "a", 1)], "pt", True, "en", [TRACK])
    payload = build_details_payload(details)
    assert payload["video"] is None
    assert payload["transcript"]["translated_to"] == "en"


MD_DETAILS = TranscriptDetails(
    video=VIDEO,
    segments=[Segment(12.7, "Olá,\nmundo", 2.0), Segment(65, "fim", 1.0)],
    language_code="pt",
    is_generated=True,
    translated_to=None,
    tracks=[TRACK],
)


def test_format_markdown_with_video_metadata():
    assert format_markdown(MD_DETAILS) == (
        "# Título\n"
        "\n"
        "- **Canal:** Canal\n"
        "- **Duração:** 00:22:29\n"
        "- **Publicado em:** 2026-10-27\n"
        "- **Link:** https://www.youtube.com/watch?v=xmK_BsRR9mk\n"
        "- **Transcrição:** pt (automática)\n"
        "\n"
        "## Transcrição\n"
        "\n"
        "**[00:00:12]** Olá,\nmundo\n"
        "\n"
        "**[00:01:05]** fim\n"
    )


def test_format_markdown_without_video_uses_generic_title_and_skips_video_fields():
    details = MD_DETAILS._replace(video=None, is_generated=False)
    assert format_markdown(details) == (
        "# Transcrição\n"
        "\n"
        "- **Transcrição:** pt (manual)\n"
        "\n"
        "**[00:00:12]** Olá,\nmundo\n"
        "\n"
        "**[00:01:05]** fim\n"
    )


def test_format_markdown_mentions_translation():
    details = MD_DETAILS._replace(translated_to="en")
    assert "- **Transcrição:** pt (automática), traduzida para en\n" in format_markdown(details)


def test_format_markdown_skips_blank_segments():
    details = MD_DETAILS._replace(segments=[Segment(0, "  ", 1), Segment(5, "ok", 1)])
    markdown = format_markdown(details)
    assert "**[00:00:05]** ok\n" in markdown
    assert "**[00:00:00]**" not in markdown


def test_format_markdown_does_not_alter_segment_text():
    details = MD_DETAILS._replace(segments=[Segment(0, "isso *não* é # alterado", 1)])
    assert "**[00:00:00]** isso *não* é # alterado\n" in format_markdown(details)


def test_build_details_payload_includes_markdown():
    payload = build_details_payload(MD_DETAILS)
    assert payload["markdown"] == format_markdown(MD_DETAILS)
