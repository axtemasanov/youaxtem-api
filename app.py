import os
import uuid
import threading
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
import yt_dlp

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def cleanup_old_files():
    while True:
        try:
            now = time.time()
            for f in os.listdir(DOWNLOAD_DIR):
                path = os.path.join(DOWNLOAD_DIR, f)
                if os.path.isfile(path) and now - os.path.getmtime(path) > 3600:
                    os.remove(path)
        except:
            pass
        time.sleep(600)

threading.Thread(target=cleanup_old_files, daemon=True).start()

@app.route("/")
def home():
    return jsonify({"ok": True})

@app.route("/api/health")
def health():
    return jsonify({"ok": True})

def download_via_cobalt(url, file_id):
    """Запасной путь - через Cobalt"""
    try:
        r = requests.post(
            "https://api.cobalt.tools/api/json",
            json={"url": url, "videoQuality": "720", "download": True},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30
        )
        data = r.json()
        dl_url = data.get("url", "")
        title = data.get("filename", "video")
        if not dl_url:
            return None, None
        if "." in title:
            title = title.rsplit(".", 1)[0]

        # Скачиваем файл с Cobalt
        resp = requests.get(dl_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120, stream=True)
        if resp.status_code != 200:
            return None, None
        ext = "mp4"
        filename = file_id + "." + ext
        path = os.path.join(DOWNLOAD_DIR, filename)
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return filename, title
    except Exception as e:
        print("cobalt error:", e)
        return None, None

@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "no url"}), 400
    if "youtube.com" not in url and "youtu.be" not in url:
        return jsonify({"error": "only youtube links"}), 400

    file_id = uuid.uuid4().hex[:12]
    out_template = os.path.join(DOWNLOAD_DIR, file_id + ".%(ext)s")

    # Путь 1: yt-dlp с разными клиентами
    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 60,
        "retries": 3,
        "force_ipv4": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "ios", "mweb"],
                "player_skip": ["configs"],
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            filename = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(file_id):
                    filename = f
                    break
            if filename:
                download_url = request.host_url + "files/" + filename
                return jsonify({"ok": True, "title": title, "filename": filename, "downloadUrl": download_url})
    except Exception as e:
        print("yt-dlp failed, trying cobalt:", e)

    # Путь 2: Cobalt - если yt-dlp не смог
    filename, title = download_via_cobalt(url, file_id)
    if filename:
        download_url = request.host_url + "files/" + filename
        return jsonify({"ok": True, "title": title or "video", "filename": filename, "downloadUrl": download_url})

    return jsonify({"error": "YouTube заблокировал сервер, попробуйте другое видео"}), 500

@app.route("/files/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
