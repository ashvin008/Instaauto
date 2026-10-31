"""Gets the Short's video file: a manual copy in videos/ if present, otherwise yt-dlp."""

import json
import subprocess
import tempfile
from pathlib import Path

MANUAL_DIR = Path("videos")
# Instagram accepts H.264 or HEVC video with AAC audio in an MP4 container.
FORMAT = "bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/b[vcodec^=avc1][ext=mp4]/bv*+ba/b"


def get_video(video_id: str, out_dir: Path, cookies: str | None = None) -> Path:
    manual = MANUAL_DIR / f"{video_id}.mp4"
    if manual.exists():
        print(f"  Using manual file {manual}")
        return manual
    return ensure_instagram_compatible(download(video_id, out_dir, cookies))


def download(video_id: str, out_dir: Path, cookies: str | None = None) -> Path:
    import yt_dlp  # installed only when there is something to download

    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
    }
    with tempfile.TemporaryDirectory() as tmp:
        if cookies:
            cookie_file = Path(tmp) / "cookies.txt"
            cookie_file.write_text(cookies, encoding="utf-8")
            opts["cookiefile"] = str(cookie_file)
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/shorts/{video_id}"])

    path = out_dir / f"{video_id}.mp4"
    if not path.exists():
        raise RuntimeError(f"yt-dlp finished but {path} was not created")
    return path


def video_codec(path: Path) -> str:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    streams = json.loads(out).get("streams", [])
    return streams[0]["codec_name"] if streams else ""


def ensure_instagram_compatible(path: Path) -> Path:
    codec = video_codec(path)
    if codec in ("h264", "hevc"):
        return path
    print(f"  Video codec is {codec!r}; re-encoding to H.264 for Instagram")
    out = path.with_name(f"{path.stem}_h264.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)],
        check=True,
    )
    return out
