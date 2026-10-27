from typing import NamedTuple


class VideoInfo(NamedTuple):
    video_id: str
    title: str
    channel: str
    duration_seconds: int
    view_count: int
    published_at: str
    thumbnail_url: str
    native_language: str | None
