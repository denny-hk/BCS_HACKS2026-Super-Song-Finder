import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import requests

from .base import MusicProvider

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

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


def clamp_limit(value, maximum):
    """Clamp a numeric page size to a sane range."""
    return max(1, min(int(value), maximum))


def normalize_text(value):
    """Normalize text for approximate title and artist matching."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(
        char for char in value if not unicodedata.combining(char)
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
        raise ValueError(f"Unsupported storefront code: {country}")

    response = requests.get(
        ITUNES_SEARCH_URL,
        params={
            "term": query,
            "country": country,
            "media": "music",
            "entity": "song",
            "limit": clamp_limit(limit, 25),
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
        title_score = text_similarity(track_name, candidate.get("title", ""))
        artist_score = text_similarity(artist_name, candidate.get("artist", ""))

        score = (title_score * 0.6) + (artist_score * 0.4)

        if score > best_score:
            best_score = score
            best_match = candidate

    if (
        best_match
        and text_similarity(track_name, best_match.get("title", "")) >= 0.78
        and text_similarity(artist_name, best_match.get("artist", "")) >= 0.75
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
            executor.submit(find_apple_match, track_name, artist_name, country): country
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


class AppleMusicProvider(MusicProvider):
    """Apple Music/iTunes catalog provider."""

    def search(self, query, country="us", limit=10):
        return search_itunes(query, country=country, limit=limit)

    def get_restrictions(self, resource_id, **kwargs):
        return None

    def check_regions(self, track_name, artist_name, countries=None):
        return check_apple_regions(track_name, artist_name, countries)


APPLE_MUSIC_PROVIDER = AppleMusicProvider()
