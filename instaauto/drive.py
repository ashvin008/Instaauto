"""Reads videos from a private Google Drive folder through a service account.

The folder must be shared (as Editor) with the service account's email, so it
can download videos and move them into the Posted / Failed subfolders.
"""

import json
from pathlib import Path

import requests

API = "https://www.googleapis.com/drive/v3/files"
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"
POSTED = "Posted"
FAILED = "Failed"


def folder_id_from(value: str) -> str:
    """Accepts a bare folder ID or a full https://drive.google.com/drive/folders/<id> link."""
    value = value.strip()
    if "/folders/" in value:
        value = value.split("/folders/", 1)[1]
    return value.split("?", 1)[0].strip("/")


class Drive:
    def __init__(self, credentials_json: str, folder_id: str):
        from google.oauth2 import service_account

        self.creds = service_account.Credentials.from_service_account_info(
            json.loads(credentials_json), scopes=SCOPES
        )
        self.folder_id = folder_id
        self._subfolders: dict[str, str] = {}

    def _headers(self) -> dict:
        from google.auth.transport.requests import Request

        if not self.creds.valid:
            self.creds.refresh(Request())
        return {"Authorization": f"Bearer {self.creds.token}"}

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        params = {"supportsAllDrives": "true", **kwargs.pop("params", {})}
        resp = requests.request(method, url, headers=self._headers(), params=params, timeout=60, **kwargs)
        if resp.status_code >= 400:
            try:
                message = resp.json()["error"]["message"]
            except (ValueError, KeyError):
                message = resp.text[:300]
            raise RuntimeError(f"Google Drive {method} failed ({resp.status_code}): {message}")
        return resp

    def _children(self, extra_query: str = "") -> list[dict]:
        files, page = [], None
        while True:
            params = {
                "q": f"'{self.folder_id}' in parents and trashed = false{extra_query}",
                "fields": "nextPageToken, files(id, name, mimeType, createdTime)",
                "pageSize": 1000,
                "includeItemsFromAllDrives": "true",
            }
            if page:
                params["pageToken"] = page
            data = self._request("GET", API, params=params).json()
            files += data.get("files", [])
            page = data.get("nextPageToken")
            if not page:
                return files

    def list_folder(self) -> tuple[list[dict], dict[str, str]]:
        """Returns (videos oldest-first, {file stem: caption .txt file ID}). Subfolders are ignored."""
        children = self._children()
        videos = sorted(
            (f for f in children if f["mimeType"].startswith("video/")),
            key=lambda f: f["createdTime"],
        )
        captions = {Path(f["name"]).stem: f["id"] for f in children if f["name"].lower().endswith(".txt")}
        return videos, captions

    def read_text(self, file_id: str) -> str:
        resp = self._request("GET", f"{API}/{file_id}", params={"alt": "media"})
        return resp.content.decode("utf-8-sig").strip()

    def download(self, file_id: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        resp = self._request("GET", f"{API}/{file_id}", params={"alt": "media"}, stream=True)
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        return dest

    def _subfolder(self, name: str) -> str:
        if name not in self._subfolders:
            found = self._children(f" and mimeType = '{FOLDER_MIME}' and name = '{name}'")
            if found:
                self._subfolders[name] = found[0]["id"]
            else:
                created = self._request(
                    "POST", API, json={"name": name, "mimeType": FOLDER_MIME, "parents": [self.folder_id]}
                ).json()
                self._subfolders[name] = created["id"]
        return self._subfolders[name]

    def move(self, file_id: str, subfolder: str) -> None:
        self._request(
            "PATCH", f"{API}/{file_id}",
            params={"addParents": self._subfolder(subfolder), "removeParents": self.folder_id},
        )
