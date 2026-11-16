import os
import uuid
import threading
import time
import re
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

def get_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

def download_file_from_url(dl_url, file_id, title):
    try:
        resp = requests.get(dl_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120, stream=True)
        if resp.status_code != 200:
            return None
        ext = "mp4"
        if "video/webm" in resp.headers.get("Content-Type", ""):
            ext = "webm"
        filename = file_id + "." + ext
        path = os.path.join(DOWNLOAD_DIR, filename)
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        if os.path.getsize(path) < 10000:
            os.remove(path)
            return None
        return filename
    except Exception as e:
        print("download file error:", e)
        return None

def try_piped(video_id, file_id):
    hosts = [
        "pipedapi.kavin.rocks",
        "pipedapi.adminforge.de",
        "api.piped.private.coffee",
        "pipedapi.reallyaweso.me",
        "pipedapi.leptons.xyz",
        "pipedapi.ducks.party",
    ]
    for host in hosts:
        try:
            r = requests.get(f"https://{host}/streams/{video_id}", timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            data = r.json()
            title = data.get("title", "video")
            streams = data.get("videoStreams", []) or []
            # Сначала ищем mp4 с аудио
            best = None
            best_q = 0
            for s in streams:
                url = s.get("url", "")
                if not url:
                    continue
                mime = s.get("mimeType", "")
                if "video/mp4" not in mime:
                    continue
                q = int(s.get("quality", "0").replace("p", "") or 0)
                # Берём 720 или ниже, чтобы было с аудио
                if q <= 720 and q > best_q:
                    best_q = q
                    best = url
            if not best and streams:
                best = streams[0].get("url", "")
            if best:
                filename = download_file_from_url(best, file_id, title)
                if filename:
                    print(f"piped ok: {host}")
                    return filename, title
        except Exception as e:
            print(f"piped {host} fail:", e)
            continue
    return None, None

def try_invidious(video_id, file_id):
    hosts = [
        "inv.nadeko.net",
        "yewtu.be",
        "invidious.jing.rocks",
        "iv.melmac.space",
        "invidious.f5.si",
    ]
    for host in hosts:
        try:
            r = requests.get(f"https://{host}/api/v1/videos/{video_id}", timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            data = r.json()
            title = data.get("title", "video")
            formats = data.get("formatStreams", []) or data.get("formats", []) or []
            best = None
            best_q = 0
            for fmt in formats:
                url = fmt.get("url", "")
                if not url:
                    continue
                q_str = fmt.get("qualityLabel", "0").replace("p", "")
                try:
                    q = int(q_str)
                except:
                    q = 0
                if q <= 720 and q > best_q:
                    best_q = q
                    best = url
            if not best and formats:
                best = formats[0].get("url", "")
            if best:
                filename = download_file_from_url(best, file_id, title)
                if filename:
                    print(f"invidious ok: {host}")
                    return filename, title
        except Exception as e:
            print(f"invidious {host} fail:", e)
            continue
    return None, None

def try_cobalt(url, file_id):
    instances = [
        "https://api.cobalt.tools/api/json",
        "https://co.wuk.sh/api/json",
        "https://cobalt-api.kavin.rocks/api/json",
    ]
    for api in instances:
        try:
            r = requests.post(api, json={"url": url, "videoQuality": "720", "download": True}, headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=30)
            data = r.json()
            dl_url = data.get("url", "")
            title = data.get("filename", "video")
            if "." in title:
                title = title.rsplit(".", 1)[0]
            if not dl_url:
                continue
            filename = download_file_from_url(dl_url, file_id, title)
            if filename:
                print(f"cobalt ok: {api}")
                return filename, title
        except Exception as e:
            print(f"cobalt {api} fail:", e)
            continue
    return None, None

@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "no url"}), 400
    if "youtube.com" not in url and "youtu.be" not in url:
        return jsonify({"error": "only youtube links"}), 400

    video_id = get_video_id(url)
    file_id = uuid.uuid4().hex[:12]

    # Путь 1: yt-dlp (если вдруг разблокируется)
    try:
        out_template = os.path.join(DOWNLOAD_DIR, file_id + ".%(ext)s")
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": out_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 2,
            "http_headers": {"User-Agent": "Mozilla/5.0"},
            "extractor_args": {"youtube": {"player_client": ["android", "web", "ios"]}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(file_id):
                    download_url = request.host_url + "files/" + f
                    return jsonify({"ok": True, "title": title, "filename": f, "downloadUrl": download_url})
    except Exception as e:
        print("yt-dlp fail:", e)

    # Путь 2: Piped
    if video_id:
        filename, title = try_piped(video_id, file_id)
        if filename:
            download_url = request.host_url + "files/" + filename
            return jsonify({"ok": True, "title": title, "filename": filename, "downloadUrl": download_url})

        # Путь 3: Invidious
        filename, title = try_invidious(video_id, file_id)
        if filename:
            download_url = request.host_url + "files/" + filename
            return jsonify({"ok": True, "title": title, "filename": filename, "downloadUrl": download_url})

    # Путь 4: Cobalt
    filename, title = try_cobalt(url, file_id)
    if filename:
        download_url = request.host_url + "files/" + filename
        return jsonify({"ok": True, "title": title or "video", "filename": filename, "downloadUrl": download_url})

    return jsonify({"error": "Все сервера заблокированы, попробуйте через минуту"}), 500

@app.route("/files/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
