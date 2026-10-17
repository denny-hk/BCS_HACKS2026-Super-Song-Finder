import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)
API_KEY = os.getenv("YOUTUBE_API_KEY")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search_song():
    query = (request.form.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Please enter a song name."}), 400

    if not API_KEY:
        return jsonify({"error": "YouTube API key is not configured."}), 500

    # Step 1: Search YouTube for the video ID
    search_params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 1,
        "key": API_KEY,
    }
    search_res = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params=search_params,
        timeout=10,
    )
    search_data = search_res.json()

    if search_res.status_code != 200 or not search_data.get("items"):
        return jsonify({"error": "Song not found on YouTube"})

    item = search_data["items"][0]
    video_id = item["id"]["videoId"]
    title = item["snippet"]["title"]
    channel = item["snippet"]["channelTitle"]
    thumbnail = item["snippet"]["thumbnails"]["medium"]["url"]

    # Step 2: Get video details to check region restrictions
    details_res = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "contentDetails", "id": video_id, "key": API_KEY},
        timeout=10,
    )
    details_data = details_res.json()

    restrictions = None
    if details_data.get("items"):
        content_details = details_data["items"][0]["contentDetails"]
        restrictions = content_details.get(
            "regionRestriction", "No restrictions (Available Worldwide)"
        )

    return jsonify(
        {
            "title": title,
            "channel": channel,
            "thumbnail": thumbnail,
            "videoId": video_id,
            "restrictions": restrictions,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
