from flask import Flask, request, jsonify
import yt_dlp
import os
import requests

app = Flask(__name__)

@app.route('/')
def home():
    return "youaxtem API is alive!"

@app.route('/get')
def get_video():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "no url"}), 400

    if "youtube.com" not in url and "youtu.be" not in url:
        url = f"https://www.youtube.com/watch?v={url}"

    # === ПОПЫТКА 1: yt-dlp с обходом (притворяемся iOS) ===
    ydl_opts = {
        'format': 'best[ext=mp4][height<=720]/best[ext=mp4]/best',
        'quiet': True,
        'noplaylist': True,
        'no_warnings': True,
        'socket_timeout': 30,
        # Вот это самое главное - обход блокировки YouTube
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        },
        'impersonate': 'chrome',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get('url'):
                return jsonify({
                    "title": info.get('title', 'video'),
                    "url": info.get('url'),
                    "thumbnail": info.get('thumbnail', ''),
                    "duration": info.get('duration', 0),
                    "source": "yt-dlp-ios"
                })
    except Exception as e:
        print(f"yt-dlp failed: {e}")

    # === ПОПЫТКА 2: Cobalt как запасной ===
    try:
        r = requests.post(
            "https://api.cobalt.tools/api/json",
            json={"url": url, "videoQuality": "720", "download": True},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30
        )
        data = r.json()
        if data.get('url'):
            return jsonify({
                "title": data.get('filename', 'video').rsplit('.', 1)[0],
                "url": data.get('url'),
                "thumbnail": "",
                "duration": 0,
                "source": "cobalt"
            })
    except Exception as e:
        print(f"cobalt failed: {e}")

    return jsonify({"error": "YouTube blocked, try another video"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
