from flask import Flask, request, jsonify
import yt_dlp
import os

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

    ydl_opts = {
        'format': 'best[ext=mp4][height<=720]/best[ext=mp4]/best',
        'quiet': True,
        'noplaylist': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "title": info.get('title', 'video'),
                "url": info.get('url'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": info.get('duration', 0)
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
