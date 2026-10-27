from collections.abc import Iterable

from ytscript.models.segment import Segment
from ytscript.models.transcript import TranscriptDetails, TranscriptTrack
from ytscript.models.video import VideoInfo

_FALLBACK_SECONDS = 1.0
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_srt_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _end_times(segments: list[Segment]) -> list[float]:
    ends = []
    for index, segment in enumerate(segments):
        next_start = segments[index + 1].start if index + 1 < len(segments) else None
        if segment.duration > 0:
            end = segment.start + segment.duration
            if next_start is not None and next_start > segment.start:
                end = min(end, next_start)
        elif next_start is not None and next_start > segment.start:
            end = next_start
        else:
            end = segment.start + _FALLBACK_SECONDS
        ends.append(end)
    return ends


def format_transcript(segments: Iterable[Segment]) -> str:
    blocks = []
    for segment in segments:
        text = _clean_text(segment.text)
        if text:
            blocks.append(f"[{format_timestamp(segment.start)}] {text}")
    return "\n\n".join(blocks)


def format_srt(segments: Iterable[Segment]) -> str:
    segments = list(segments)
    blocks = []
    for segment, end in zip(segments, _end_times(segments)):
        text = _clean_text(segment.text)
        if not text:
            continue
        number = len(blocks) + 1
        start_label = format_srt_timestamp(segment.start)
        end_label = format_srt_timestamp(end)
        blocks.append(f"{number}\n{start_label} --> {end_label}\n{text}\n")
    return "\n".join(blocks)


def format_markdown(details: TranscriptDetails) -> str:
    video = details.video
    kind = "automática" if details.is_generated else "manual"
    transcript_info = f"{details.language_code} ({kind})"
    if details.translated_to:
        transcript_info += f", traduzida para {details.translated_to}"

    lines = [f"# {video.title}" if video else "# Transcrição", ""]
    if video:
        lines += [
            f"- **Canal:** {video.channel}",
            f"- **Duração:** {format_timestamp(video.duration_seconds)}",
            f"- **Publicado em:** {video.published_at[:10]}",
            f"- **Link:** {WATCH_URL.format(video_id=video.video_id)}",
        ]
    lines += [f"- **Transcrição:** {transcript_info}", ""]
    if video:
        lines += ["## Transcrição", ""]
    for segment in details.segments:
        text = _clean_text(segment.text)
        if text:
            lines += [f"**[{format_timestamp(segment.start)}]** {text}", ""]
    return "\n".join(lines)


def build_transcript_payload(segments: Iterable[Segment]) -> dict:
    segments = list(segments)
    return {
        "segments": [
            {
                "start": segment.start,
                "end": end,
                "timestamp": format_timestamp(segment.start),
                "text": segment.text,
            }
            for segment, end in zip(segments, _end_times(segments))
        ],
        "text": format_transcript(segments),
        "srt": format_srt(segments),
    }


def _video_payload(video: VideoInfo) -> dict:
    return {
        "id": video.video_id,
        "title": video.title,
        "channel": video.channel,
        "duration_seconds": video.duration_seconds,
        "view_count": video.view_count,
        "published_at": video.published_at,
        "thumbnail_url": video.thumbnail_url,
        "native_language": video.native_language,
    }


def _track_payload(track: TranscriptTrack) -> dict:
    return {
        "language_code": track.language_code,
        "language": track.language,
        "is_generated": track.is_generated,
        "translation_languages": [
            {"language_code": code, "language": name} for code, name in track.translation_languages
        ],
    }


def build_details_payload(details: TranscriptDetails) -> dict:
    return {
        "video": _video_payload(details.video) if details.video else None,
        "transcript": {
            "language_code": details.language_code,
            "is_generated": details.is_generated,
            "translated_to": details.translated_to,
        },
        "tracks": [_track_payload(track) for track in details.tracks],
        **build_transcript_payload(details.segments),
        "markdown": format_markdown(details),
    }
