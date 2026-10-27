import json

import requests

from infra.errors import VideoMetadataError

WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
THUMBNAIL_URL = "https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
PLAYER_RESPONSE_MARKER = "ytInitialPlayerResponse"
REQUEST_TIMEOUT_SECONDS = 15


def _extract_player_response(html: str) -> dict:
    marker = html.find(PLAYER_RESPONSE_MARKER)
    start = html.find("{", marker) if marker != -1 else -1
    if start == -1:
        raise VideoMetadataError()
    try:
        data, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError as error:
        raise VideoMetadataError() from error
    return data


def _native_language(captions: dict) -> str | None:
    audio_tracks = captions.get("audioTracks") or []
    index = captions.get("defaultAudioTrackIndex")
    if isinstance(index, int) and 0 <= index < len(audio_tracks):
        track_id = audio_tracks[index].get("audioTrackId")
        if track_id:
            return track_id.split(".")[0]
    for track in captions.get("captionTracks") or []:
        if track.get("kind") == "asr":
            return track.get("languageCode")
    return None


def parse_player_response(html: str) -> dict:
    data = _extract_player_response(html)
    details = data.get("videoDetails") or {}
    try:
        video_id = details["videoId"]
        metadata = {
            "video_id": video_id,
            "title": details["title"],
            "channel": details["author"],
            "duration_seconds": int(details["lengthSeconds"]),
            "view_count": int(details["viewCount"]),
            "published_at": data["microformat"]["playerMicroformatRenderer"]["publishDate"],
            "thumbnail_url": THUMBNAIL_URL.format(video_id=video_id),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise VideoMetadataError() from error
    captions = (data.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}
    metadata["native_language"] = _native_language(captions)
    return metadata


def fetch_video_metadata(video_id: str) -> dict:
    try:
        response = requests.get(
            WATCH_URL.format(video_id=video_id),
            headers={"Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise VideoMetadataError() from error
    return parse_player_response(response.text)
