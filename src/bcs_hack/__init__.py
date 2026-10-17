import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
import requests

from .providers import (
    APPLE_MUSIC_PROVIDER,
    APPLE_STOREFRONTS,
    MusicProvider,
    SPOTIFY_PROVIDER,
    SpotifyProvider,
    YOUTUBE_PROVIDER,
    YouTubeMusicProvider,
)
from .providers import apple as apple_provider_module
from .providers import spotify as spotify_provider_module
from .providers import youtube as youtube_provider_module

load_dotenv()

app = Flask(__name__)

SPOTIFY_CLIENT_ID = spotify_provider_module.SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET = spotify_provider_module.SPOTIFY_CLIENT_SECRET
SPOTIFY_ACCESS_TOKEN = spotify_provider_module.SPOTIFY_ACCESS_TOKEN
YOUTUBE_API_KEY = youtube_provider_module.YOUTUBE_API_KEY

SPOTIFY_TOKEN_CACHE = spotify_provider_module.SPOTIFY_TOKEN_CACHE
SPOTIFY_SEARCH_URL = spotify_provider_module.SPOTIFY_SEARCH_URL
SPOTIFY_TOKEN_URL = spotify_provider_module.SPOTIFY_TOKEN_URL
YOUTUBE_SEARCH_URL = youtube_provider_module.YOUTUBE_SEARCH_URL
YOUTUBE_VIDEO_URL = youtube_provider_module.YOUTUBE_VIDEO_URL
ITUNES_SEARCH_URL = apple_provider_module.ITUNES_SEARCH_URL


def get_spotify_token():
    return spotify_provider_module.get_spotify_token()


def format_spotify_markets(markets):
    return spotify_provider_module.format_spotify_markets(markets)


def search_spotify_track(query, market=None, limit=10):
    return SPOTIFY_PROVIDER.search(query, market=market, limit=limit)


def search_youtube_track(query, limit=10):
    return YOUTUBE_PROVIDER.search(query, limit=limit)


def get_youtube_region_restrictions(video_id):
    return youtube_provider_module.get_youtube_region_restrictions(video_id)


def normalize_text(value):
    return apple_provider_module.normalize_text(value)


def text_similarity(first, second):
    return apple_provider_module.text_similarity(first, second)


def search_itunes(query, country="us", limit=10):
    return APPLE_MUSIC_PROVIDER.search(query, country=country, limit=limit)


def find_apple_match(track_name, artist_name, country):
    return apple_provider_module.find_apple_match(track_name, artist_name, country)


def check_apple_regions(track_name, artist_name, countries=None):
    return APPLE_MUSIC_PROVIDER.check_regions(track_name, artist_name, countries)


# -------------------------
# Flask routes
# -------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search_song():
    query = (request.form.get("query") or "").strip()
    market = (request.form.get("market") or "").strip().lower()

    if not query:
        return jsonify({"error": "Please enter a song name."}), 400

    response_data = {}

    try:
        response_data["spotify"] = SPOTIFY_PROVIDER.search(
            query,
            market=market or None,
            limit=10,
        )
    except (RuntimeError, requests.RequestException) as exc:
        response_data["spotify"] = {
            "error": str(exc) if isinstance(exc, RuntimeError)
            else "Spotify search request failed."
        }

    try:
        response_data["youtube"] = YOUTUBE_PROVIDER.search(
            query,
            limit=10,
        )
    except RuntimeError as exc:
        response_data["youtube"] = {"error": str(exc)}
    except requests.RequestException:
        response_data["youtube"] = {
            "error": "YouTube search request failed."
        }

    apple_country = market if market in APPLE_STOREFRONTS else "us"

    try:
        response_data["apple_music"] = APPLE_MUSIC_PROVIDER.search(
            query,
            country=apple_country,
            limit=10,
        )
    except (ValueError, requests.RequestException):
        response_data["apple_music"] = {
            "error": "Apple Music catalog search failed."
        }

    return jsonify(response_data)


@app.route("/api/apple/regions", methods=["POST"])
def apple_regions():
    """Check a selected song in Apple/iTunes storefront catalogs."""
    data = request.get_json(silent=True) or {}

    track_name = (data.get("trackName") or "").strip()
    artist_name = (data.get("artistName") or "").strip()
    countries = data.get("countries")

    if not track_name or not artist_name:
        return jsonify({
            "error": "Both trackName and artistName are required."
        }), 400

    if countries is not None and not isinstance(countries, list):
        return jsonify({
            "error": "countries must be a list of storefront codes."
        }), 400

    results = APPLE_MUSIC_PROVIDER.check_regions(
        track_name,
        artist_name,
        countries,
    )

    return jsonify({
        "trackName": track_name,
        "artistName": artist_name,
        "checked": len(results),
        "results": results,
    })


@app.route("/api/youtube/regions", methods=["POST"])
def youtube_regions():
    """Check region restriction metadata for a selected YouTube video."""
    data = request.get_json(silent=True) or {}
    video_id = (data.get("videoId") or "").strip()

    if not video_id:
        return jsonify({"error": "videoId is required."}), 400

    try:
        result = YOUTUBE_PROVIDER.get_restrictions(video_id)
        return jsonify(result)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except requests.RequestException:
        return jsonify({
            "error": "YouTube region lookup failed."
        }), 502


def main():
    app.run(debug=True)


if __name__ == "__main__":
    main()
