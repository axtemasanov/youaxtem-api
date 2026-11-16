from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

PIPED_HOSTS = [
    "pipedapi.kavin.rocks",
    "pipedapi.adminforge.de",
    "pipedapi.reallyaweso.me",
    "pipedapi.drgns.space",
    "pipedapi.leptons.xyz",
    "pipedapi.ducks.party",
    "pipedapi-libre.kavin.rocks",
]

INVIDIOUS_HOSTS = [
    "inv.nadeko.net",
    "yewtu.be",
    "invidious.jing.rocks",
    "iv.melmac.space",
]

@app.route('/')
def home():
    return "youaxtem API v3 is alive!"

@app.route('/get')
def get_video():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "no url"}), 400

    # вытаскиваем ID
    video_id = url
    if "v=" in url:
        video_id = url.split("v=")[1].split("&")[0].split("?")[0]
    elif "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0].split("&")[0]
    elif "shorts/" in url:
        video_id = url.split("shorts/")[1].split("?")[0].split("/")[0]

    # === 1. PIPED ===
    for host in PIPED_HOSTS:
        try:
            r = requests.get(f"https://{host}/streams/{video_id}", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                streams = data.get("videoStreams", [])
                # ищем mp4 с аудио
                best = None
                for s in streams:
                    if s.get("format") == "MP4" and s.get("audio"):
                        best = s.get("url")
                        break
                if not best and streams:
                    best = streams[0].get("url")
                if best:
                    return jsonify({
                        "title": data.get("title", "video"),
                        "url": best,
                        "thumbnail": data.get("thumbnail", ""),
                        "source": f"piped-{host}"
                    })
        except Exception as e:
            print(f"piped {host} fail: {e}")
            continue

    # === 2. INVIDIOUS ===
    for host in INVIDIOUS_HOSTS:
        try:
            r = requests.get(f"https://{host}/api/v1/videos/{video_id}", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                formats = data.get("formatStreams", []) or data.get("formats", [])
                best = None
                for f in formats:
                    if "mp4" in f.get("type", ""):
                        best = f.get("url")
                        break
                if best:
                    return jsonify({
                        "title": data.get("title", "video"),
                        "url": best,
                        "thumbnail": data.get("videoThumbnails", [{}])[0].get("url", ""),
                        "source": f"invidious-{host}"
                    })
        except Exception as e:
            print(f"invidious {host} fail: {e}")
            continue

    # === 3. COBALT ===
    try:
        r = requests.post(
            "https://api.cobalt.tools/api/json",
            json={"url": f"https://www.youtube.com/watch?v={video_id}", "videoQuality": "720", "download": True},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        data = r.json()
        if data.get("url"):
            return jsonify({
                "title": data.get("filename", "video").rsplit('.', 1)[0],
                "url": data.get("url"),
                "source": "cobalt"
            })
    except Exception as e:
        print(f"cobalt fail: {e}")

    return jsonify({"error": "all methods failed"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"YOU_AXTEM server: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
