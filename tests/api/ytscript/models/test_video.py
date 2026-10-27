from ytscript.models.video import VideoInfo


def test_video_info_fields():
    video = VideoInfo(
        video_id="xmK_BsRR9mk",
        title="Título",
        channel="Canal",
        duration_seconds=1349,
        view_count=7671,
        published_at="2026-10-27T08:00:22-07:00",
        thumbnail_url="https://i.ytimg.com/vi/xmK_BsRR9mk/hqdefault.jpg",
        native_language="pt",
    )
    assert video.title == "Título"
    assert video.duration_seconds == 1349
    assert video.native_language == "pt"
