import os
import time

import requests

from .base import MusicProvider

SPOTIFY_CLIENT_ID = (
    os.getenv("SPOTIFY_CLIENT_ID")
    or os.getenv("SPOTIFY_API_KEY")
)
SPOTIFY_CLIENT_SECRET = (
    os.getenv("SPOTIFY_CLIENT_SECRET")
    or os.getenv("SPOTIFY_API_SECRET")
)
SPOTIFY_ACCESS_TOKEN = os.getenv("SPOTIFY_ACCESS_TOKEN")

SPOTIFY_TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0.0,
}

SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


def clamp_limit(value, maximum):
    """Clamp a numeric page size to a sane range."""
    return max(1, min(int(value), maximum))


def get_spotify_token():
    """Return a valid Spotify access token."""
    now = time.time()

    cached_token = SPOTIFY_TOKEN_CACHE["access_token"]
    expires_at = SPOTIFY_TOKEN_CACHE["expires_at"]

    if cached_token and now < expires_at - 30:
        return cached_token

    if SPOTIFY_ACCESS_TOKEN:
        SPOTIFY_TOKEN_CACHE["access_token"] = SPOTIFY_ACCESS_TOKEN
        SPOTIFY_TOKEN_CACHE["expires_at"] = now + 3600
        return SPOTIFY_ACCESS_TOKEN

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("Spotify API credentials are not configured.")

    response = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=10,
    )
    response.raise_for_status()

    token_data = response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        raise RuntimeError(
            "Spotify token response did not include an access token."
        )

    SPOTIFY_TOKEN_CACHE["access_token"] = access_token
    SPOTIFY_TOKEN_CACHE["expires_at"] = (
        now + int(token_data.get("expires_in", 3600))
    )

    return access_token


def format_spotify_markets(markets):
    regions = sorted(set(markets or []))

    if not regions:
        return "No market information returned"

    return (
        f"Available in {len(regions)} markets: "
        + ", ".join(regions[:12])
        + (", ..." if len(regions) > 12 else "")
    )


def search_spotify_track(query, market=None, limit=10):
    """Return multiple Spotify track candidates."""
    token = get_spotify_token()

    params = {
        "q": query,
        "type": "track",
        "limit": clamp_limit(limit, 10),
    }

    if market:
        params["market"] = market.upper()

    response = requests.get(
        SPOTIFY_SEARCH_URL,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()

    items = response.json().get("tracks", {}).get("items", [])
    results = []

    for track in items:
        artists = ", ".join(
            artist["name"] for artist in track.get("artists", [])
        )

        album = track.get("album", {})
        images = album.get("images", [])

        results.append({
            "title": track.get("name"),
            "artist": artists,
            "album": album.get("name"),
            "thumbnail": images[-1].get("url") if images else None,
            "trackId": track.get("id"),
            "spotifyUrl": track.get("external_urls", {}).get("spotify"),
            "previewUrl": track.get("preview_url"),
            "popularity": track.get("popularity"),
            "restrictions": format_spotify_markets(
                track.get("available_markets", [])
            ),
        })

    return results


class SpotifyProvider(MusicProvider):
    """Spotify-backed music search provider."""

    def search(self, query, market=None, limit=10):
        return search_spotify_track(query, market=market, limit=limit)

    def get_restrictions(self, resource_id, **kwargs):
        return None


SPOTIFY_PROVIDER = SpotifyProvider()
