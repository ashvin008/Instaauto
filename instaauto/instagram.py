"""Publishes Reels through the official Instagram API (Instagram Login).

Uses a resumable upload, so the video is sent straight from the runner and
does not need to be hosted at a public URL first.
"""

import time
from pathlib import Path

import requests

CAPTION_LIMIT = 2200


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, token: str, version: str = "v23.0"):
        self.token = token
        self.version = version
        self.base = f"https://graph.instagram.com/{version}"
        self._user_id: str | None = None

    def _call(self, method: str, path: str, **params) -> dict:
        params["access_token"] = self.token
        if method == "GET":
            resp = requests.get(self.base + path, params=params, timeout=60)
        else:
            resp = requests.post(self.base + path, data=params, timeout=60)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise InstagramError(f"{method} {path} failed ({resp.status_code}): {err.get('message') or resp.text[:300]}")
        return data

    def me(self) -> dict:
        return self._call("GET", "/me", fields="user_id,username")

    @property
    def user_id(self) -> str:
        if self._user_id is None:
            self._user_id = self.me()["user_id"]
        return self._user_id

    def publish_reel(self, video: Path, caption: str, timeout: int = 900) -> str:
        """Uploads and publishes a Reel; returns the new Instagram media ID."""
        container = self._call(
            "POST", f"/{self.user_id}/media",
            media_type="REELS",
            upload_type="resumable",
            caption=caption[:CAPTION_LIMIT],
            share_to_feed="true",
        )
        container_id = container["id"]
        upload_uri = container.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{self.version}/{container_id}"

        print(f"  Uploading {video.stat().st_size / 1_000_000:.1f} MB to Instagram")
        with video.open("rb") as f:
            resp = requests.post(
                upload_uri,
                headers={
                    "Authorization": f"OAuth {self.token}",
                    "offset": "0",
                    "file_size": str(video.stat().st_size),
                },
                data=f,
                timeout=600,
            )
        if resp.status_code >= 400:
            raise InstagramError(f"Video upload failed ({resp.status_code}): {resp.text[:300]}")

        self._wait_until_ready(container_id, timeout)
        return self._call("POST", f"/{self.user_id}/media_publish", creation_id=container_id)["id"]

    def _wait_until_ready(self, container_id: str, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self._call("GET", f"/{container_id}", fields="status_code,status")
            status = info.get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Instagram could not process the video: {info.get('status') or status}")
            time.sleep(10)
        raise InstagramError(f"Instagram was still processing the video after {timeout}s")
