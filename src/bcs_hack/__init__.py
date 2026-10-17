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
    query = request.form.get("query")

    # Step 1: Search YouTube for the video ID
    search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&type=video&maxResults=1&key={API_KEY}"
    search_res = requests.get(search_url).json()

    if not search_res.get("items"):
        return jsonify({"error": "Song not found on YouTube"})

    item = search_res["items"][0]
    video_id = item["id"]["videoId"]
    title = item["snippet"]["title"]
    channel = item["snippet"]["channelTitle"]
    thumbnail = item["snippet"]["thumbnails"]["medium"]["url"]

    # Step 2: Get video details to check region restrictions
    details_url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={video_id}&key={API_KEY}"
    details_res = requests.get(details_url).json()

    restrictions = None
    if details_res.get("items"):
        content_details = details_res["items"][0]["contentDetails"]
        # Check if regionRestriction exists
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
