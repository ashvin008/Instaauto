"""Makes sure a video is in a format Instagram accepts (H.264/HEVC video, AAC audio)."""

import json
import subprocess
from pathlib import Path


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
