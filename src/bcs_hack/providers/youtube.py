import os

import requests

from .base import MusicProvider

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"


def clamp_limit(value, maximum):
    """Clamp a numeric page size to a sane range."""
    return max(1, min(int(value), maximum))


def search_youtube_track(query, limit=10):
    """Return multiple YouTube video candidates."""
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YouTube API key is not configured.")

    response = requests.get(
        YOUTUBE_SEARCH_URL,
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoCategoryId": "10",
            "maxResults": clamp_limit(limit, 10),
            "key": YOUTUBE_API_KEY,
        },
        timeout=10,
    )
    response.raise_for_status()

    results = []

    for item in response.json().get("items", []):
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})

        if not video_id:
            continue

        thumbnails = snippet.get("thumbnails", {})
        thumbnail = (
            thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        results.append({
            "title": snippet.get("title"),
            "artist": snippet.get("channelTitle"),
            "channel": snippet.get("channelTitle"),
            "thumbnail": thumbnail,
            "videoId": video_id,
            "youtubeUrl": f"https://www.youtube.com/watch?v={video_id}",
            "publishedAt": snippet.get("publishedAt"),
        })

    return results


def get_youtube_region_restrictions(video_id):
    """Fetch region restrictions for one YouTube video."""
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YouTube API key is not configured.")

    response = requests.get(
        YOUTUBE_VIDEO_URL,
        params={
            "part": "contentDetails",
            "id": video_id,
            "key": YOUTUBE_API_KEY,
        },
        timeout=10,
    )
    response.raise_for_status()

    items = response.json().get("items", [])
    if not items:
        return {"status": "unknown", "message": "Video details not found"}

    details = items[0].get("contentDetails", {})
    restriction = details.get("regionRestriction", {})

    if "allowed" in restriction:
        return {
            "status": "restricted",
            "allowed": restriction["allowed"],
            "message": "Video is restricted to listed regions",
        }

    if "blocked" in restriction:
        return {
            "status": "restricted",
            "blocked": restriction["blocked"],
            "message": "Video is blocked in listed regions",
        }

    return {
        "status": "no_restrictions_listed",
        "message": "No region restrictions listed by the API",
    }


class YouTubeMusicProvider(MusicProvider):
    """YouTube-backed music search provider."""

    def search(self, query, limit=10):
        return search_youtube_track(query, limit=limit)

    def get_restrictions(self, resource_id, **kwargs):
        return get_youtube_region_restrictions(resource_id)


YOUTUBE_PROVIDER = YouTubeMusicProvider()
