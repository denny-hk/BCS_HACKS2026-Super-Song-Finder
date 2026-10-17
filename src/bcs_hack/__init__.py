import os
import time
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

# -------------------------
# API credentials
# -------------------------

SPOTIFY_CLIENT_ID = (
    os.getenv("SPOTIFY_CLIENT_ID")
    or os.getenv("SPOTIFY_API_KEY")
)
SPOTIFY_CLIENT_SECRET = (
    os.getenv("SPOTIFY_CLIENT_SECRET")
    or os.getenv("SPOTIFY_API_SECRET")
)
SPOTIFY_ACCESS_TOKEN = os.getenv("SPOTIFY_ACCESS_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

SPOTIFY_TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0.0,
}

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"

# Initial set of storefronts. More can be added later.
APPLE_STOREFRONTS = {
    "us": "United States",
    "ca": "Canada",
    "gb": "United Kingdom",
    "jp": "Japan",
    "de": "Germany",
    "fr": "France",
    "au": "Australia",
    "kr": "South Korea",
    "cn": "China",
    "hk": "Hong Kong",
    "tw": "Taiwan",
    "sg": "Singapore",
    "my": "Malaysia",
    "th": "Thailand",
    "vn": "Vietnam",
    "it": "Italy",
    "es": "Spain",
    "br": "Brazil",
    "mx": "Mexico",
    "in": "India",
}


# -------------------------
# Spotify
# -------------------------

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
        raise RuntimeError(
            "Spotify API credentials are not configured."
        )

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
        "limit": min(max(limit, 1), 10),
    }

    if market:
        params["market"] = market.upper()

    response = requests.get(
        "https://api.spotify.com/v1/search",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()

    items = response.json().get("tracks", {}).get("items", [])
    results = []

    for track in items:
        artists = ", ".join(
            artist["name"]
            for artist in track.get("artists", [])
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


# -------------------------
# YouTube
# -------------------------

def search_youtube_track(query, limit=10):
    """Return multiple YouTube video candidates."""
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YouTube API key is not configured.")

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoCategoryId": "10",
            "maxResults": min(max(limit, 1), 10),
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
            "youtubeUrl": (
                f"https://www.youtube.com/watch?v={video_id}"
            ),
            "publishedAt": snippet.get("publishedAt"),
        })

    return results


def get_youtube_region_restrictions(video_id):
    """Fetch region restrictions for one YouTube video."""
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YouTube API key is not configured.")

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
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


# -------------------------
# Apple Music / iTunes
# -------------------------

def normalize_text(value):
    """Normalize text for approximate title and artist matching."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    value = value.lower()
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(value.split())


def text_similarity(first, second):
    return SequenceMatcher(
        None,
        normalize_text(first),
        normalize_text(second),
    ).ratio()


def search_itunes(query, country="us", limit=10):
    """Search the iTunes catalog in one storefront."""
    country = country.lower()

    if country not in APPLE_STOREFRONTS:
        raise ValueError(
            f"Unsupported storefront code: {country}"
        )

    response = requests.get(
        ITUNES_SEARCH_URL,
        params={
            "term": query,
            "country": country,
            "media": "music",
            "entity": "song",
            "limit": min(max(limit, 1), 25),
        },
        timeout=10,
    )
    response.raise_for_status()

    results = []

    for item in response.json().get("results", []):
        results.append({
            "title": item.get("trackName"),
            "artist": item.get("artistName"),
            "album": item.get("collectionName"),
            "thumbnail": item.get("artworkUrl100"),
            "trackId": item.get("trackId"),
            "appleMusicUrl": item.get("trackViewUrl"),
            "previewUrl": item.get("previewUrl"),
            "storefront": country,
            "storefrontName": APPLE_STOREFRONTS[country],
        })

    return results


def find_apple_match(track_name, artist_name, country):
    """Look for a matching title and artist in a storefront."""
    query = f"{track_name} {artist_name}"
    candidates = search_itunes(query, country=country, limit=10)

    best_match = None
    best_score = 0.0

    for candidate in candidates:
        title_score = text_similarity(
            track_name, candidate.get("title", "")
        )
        artist_score = text_similarity(
            artist_name, candidate.get("artist", "")
        )

        score = (title_score * 0.6) + (artist_score * 0.4)

        if score > best_score:
            best_score = score
            best_match = candidate

    if (
        best_match
        and text_similarity(
            track_name, best_match.get("title", "")
        ) >= 0.78
        and text_similarity(
            artist_name, best_match.get("artist", "")
        ) >= 0.75
    ):
        return {
            "country": country,
            "countryName": APPLE_STOREFRONTS[country],
            "status": "found",
            "match": best_match,
            "similarity": round(best_score, 3),
        }

    return {
        "country": country,
        "countryName": APPLE_STOREFRONTS[country],
        "status": "not_found",
        "match": None,
    }


def check_apple_regions(track_name, artist_name, countries=None):
    """Check a selected song across multiple storefronts."""
    if countries is None:
        countries = list(APPLE_STOREFRONTS.keys())

    countries = [
        country.lower()
        for country in countries
        if country.lower() in APPLE_STOREFRONTS
    ]

    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {
            executor.submit(
                find_apple_match,
                track_name,
                artist_name,
                country,
            ): country
            for country in countries
        }

        for future in as_completed(future_map):
            country = future_map[future]

            try:
                results.append(future.result())
            except requests.RequestException:
                results.append({
                    "country": country,
                    "countryName": APPLE_STOREFRONTS[country],
                    "status": "error",
                    "message": "Catalog request failed",
                })
            except Exception:
                results.append({
                    "country": country,
                    "countryName": APPLE_STOREFRONTS[country],
                    "status": "error",
                    "message": "Could not check this storefront",
                })

    results.sort(key=lambda item: item["country"])

    return results


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

    # 1. Spotify
    try:
        response_data["spotify"] = search_spotify_track(
            query,
            market=market or None,
            limit=10,
        )
    except (RuntimeError, requests.RequestException) as exc:
        response_data["spotify"] = {
            "error": str(exc) if isinstance(exc, RuntimeError)
            else "Spotify search request failed."
        }

    # 2. YouTube
    try:
        response_data["youtube"] = search_youtube_track(
            query,
            limit=10,
        )
    except RuntimeError as exc:
        response_data["youtube"] = {"error": str(exc)}
    except requests.RequestException:
        response_data["youtube"] = {
            "error": "YouTube search request failed."
        }

    # 3. Apple Music / iTunes
    # Search the selected storefront, or the US storefront by default.
    apple_country = market if market in APPLE_STOREFRONTS else "us"

    try:
        response_data["apple_music"] = search_itunes(
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

    results = check_apple_regions(
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
        result = get_youtube_region_restrictions(video_id)
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