import os
import re
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
API_KEY = os.environ.get("YOUAXTEM_API_KEY", "change-me")
MAX_FILE_SIZE = "500M"

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}

def is_youtube_url(value: str) -> bool:
    try:
        host = urlparse(value).hostname
        return host is not None and host.lower() in YOUTUBE_HOSTS
    except Exception:
        return False

def safe_job_name() -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", uuid.uuid4().hex)

@app.get("/")
def home():
    return jsonify({"ok": True, "msg": "youaxtem API Termux version is alive!"})

@app.get("/api/health")
def health():
    return jsonify({"ok": True})

@app.post("/api/download")
def download_video():
    if request.headers.get("X-API-Key", "") != API_KEY:
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    source = str(body.get("url", "")).strip()
    if not source or not is_youtube_url(source):
        return jsonify({"error": "Нужна публичная ссылка YouTube"}), 400

    job = safe_job_name()
    output_template = str(DOWNLOAD_DIR / (job + ".%(ext)s"))
    command = [
        "yt-dlp",
        "--no-playlist",
        "--max-filesize", MAX_FILE_SIZE,
        "--merge-output-format", "mp4",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--print", "after_move:filepath",
        "-o", output_template,
        source,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15 * 60,
            check=False,
        )
    except FileNotFoundError:
        return jsonify({"error": "На сервере не установлен yt-dlp"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Загрузка заняла слишком много времени"}), 504

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "yt-dlp error").strip()[-1000:]
        return jsonify({"error": error}), 502

    files = sorted(DOWNLOAD_DIR.glob(job + ".*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return jsonify({"error": "Файл не был создан"}), 500

    file_path = files[0]
    return jsonify({
        "title": file_path.stem,
        "downloadUrl": request.host_url.rstrip("/") + "/files/" + file_path.name,
    })

@app.get("/files/<path:name>")
def serve_file(name: str):
    return send_from_directory(DOWNLOAD_DIR, name, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"YOU_AXTEM server: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
