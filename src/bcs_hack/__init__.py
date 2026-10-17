import os
import time

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

# --- Credential Configuration ---
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID") or os.getenv("SPOTIFY_API_KEY")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET") or os.getenv(
    "SPOTIFY_API_SECRET"
)
SPOTIFY_ACCESS_TOKEN = os.getenv("SPOTIFY_ACCESS_TOKEN")

# YouTube API Key Configuration
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

_SPOTIFY_TOKEN_CACHE = {"access_token": None, "expires_at": 0.0}


def get_spotify_token():
    """Return a valid Spotify access token, reusing a cached one when possible."""
    now = time.time()
    cached_token = _SPOTIFY_TOKEN_CACHE["access_token"]
    expires_at = _SPOTIFY_TOKEN_CACHE["expires_at"]

    if cached_token and now < expires_at - 30:
        return cached_token

    if SPOTIFY_ACCESS_TOKEN:
        _SPOTIFY_TOKEN_CACHE["access_token"] = SPOTIFY_ACCESS_TOKEN
        _SPOTIFY_TOKEN_CACHE["expires_at"] = now + 3600
        return SPOTIFY_ACCESS_TOKEN

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("Spotify API credentials are not configured.")

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=10,
    )
    response.raise_for_status()

    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("Spotify token request did not include an access token.")

    expires_in = int(token_data.get("expires_in", 3600))
    _SPOTIFY_TOKEN_CACHE["access_token"] = access_token
    _SPOTIFY_TOKEN_CACHE["expires_at"] = now + expires_in
    return access_token


def format_regional_availability(markets):
    """Convert Spotify country codes into a readable regional availability string."""
    regions = sorted(set(markets or []))
    if not regions:
        return "Not available in any Spotify market"
    if len(regions) <= 12:
        return f"Available in: {', '.join(regions)}"
    return f"Available in {len(regions)} markets: {', '.join(regions[:12])}, ..."


def format_regional_availability(markets):
    """Convert Spotify country codes into a readable regional availability string."""
    regions = sorted(set(markets or []))
    if not regions:
        return "Not available in any Spotify market"
    if len(regions) <= 12:
        return f"Available in: {', '.join(regions)}"
    return f"Available in {len(regions)} markets: {', '.join(regions[:12])}, ..."


def search_spotify_track(query, market=None):
    token = get_spotify_token()
    params = {"q": query, "type": "track", "limit": 1}
    if market:
        params["market"] = market.upper()

    response = requests.get(
        "https://api.spotify.com/v1/search",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    items = data.get("tracks", {}).get("items", [])
    if not items:
        return None

    track = items[0]
    artists = ", ".join(artist["name"] for artist in track.get("artists", []))
    album = track.get("album", {})
    images = album.get("images", [])
    thumbnail = images[-1].get("url") if images else None
    available_markets = track.get("available_markets", [])

    return {
        "title": track.get("name"),
        "artist": artists,
        "channel": artists,
        "album": album.get("name"),
        "thumbnail": thumbnail,
        "trackId": track.get("id"),
        "spotifyUrl": track.get("external_urls", {}).get("spotify"),
        "previewUrl": track.get("preview_url"),
        "popularity": track.get("popularity"),
        "restrictions": format_regional_availability(available_markets),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search_song():
    query = (request.form.get("query") or "").strip()
    market = (request.form.get("market") or "").strip()
    if not query:
        return jsonify({"error": "Please enter a song name."}), 400

    response_data = {}

    # 1. Search Spotify
    try:
        result = search_spotify_track(query)
    except RuntimeError as exc:
        response_data["spotify"] = {"error": str(exc)}
    except requests.RequestException:
        response_data["spotify"] = {"error": "Spotify search request failed."}

    # 2. Search YouTube
    try:
        youtube_result = search_youtube_track(query)
        if youtube_result:
            response_data["youtube"] = youtube_result
        else:
            response_data["youtube"] = {"error": "Video not found on YouTube"}
    except requests.RequestException:
        response_data["youtube"] = {"error": "YouTube search request failed."}
    except Exception as exc:
        response_data["youtube"] = {"error": str(exc)}

    return jsonify(response_data)


def main():
    app.run(debug=True)


if __name__ == "__main__":
    main()
