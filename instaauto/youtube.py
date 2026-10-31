"""Finds the channel's latest uploads.

Uses the YouTube Data API when YT_API_KEY is set (recommended), otherwise the
public RSS feed, which needs no key but has been unreliable.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; instaauto/1.0)"}


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    description: str
    url: str
    published: str


def parse_feed(xml_text: str) -> list[Video]:
    root = ET.fromstring(xml_text)
    videos = []
    for entry in root.findall("atom:entry", NS):
        link = entry.find("atom:link", NS)
        videos.append(
            Video(
                id=entry.findtext("yt:videoId", "", NS),
                title=entry.findtext("atom:title", "", NS),
                description=entry.findtext("media:group/media:description", "", NS),
                url=link.get("href", "") if link is not None else "",
                published=entry.findtext("atom:published", "", NS),
            )
        )
    # The feed is newest-first; process oldest-first so Reels go out in the same order.
    return sorted(videos, key=lambda v: v.published)


def fetch_feed(channel_id: str) -> list[Video]:
    resp = requests.get(FEED_URL.format(channel_id), headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"YouTube RSS feed returned HTTP {resp.status_code}. "
            "Set the YT_API_KEY secret to use the YouTube Data API instead (see README)."
        )
    return parse_feed(resp.text)


def parse_api(data: dict) -> list[Video]:
    videos = []
    for item in data.get("items", []):
        snippet = item["snippet"]
        if snippet.get("title") in ("Private video", "Deleted video"):
            continue
        video_id = snippet["resourceId"]["videoId"]
        videos.append(
            Video(
                id=video_id,
                title=snippet.get("title", ""),
                description=snippet.get("description", ""),
                url=f"https://www.youtube.com/watch?v={video_id}",
                published=snippet.get("publishedAt", ""),
            )
        )
    return sorted(videos, key=lambda v: v.published)


def fetch_api(channel_id: str, api_key: str) -> list[Video]:
    # Every channel's uploads live in a playlist whose ID is the channel ID with UC -> UU.
    # One call costs 1 unit of the free 10,000/day quota.
    resp = requests.get(
        API_URL,
        params={"part": "snippet", "playlistId": "UU" + channel_id[2:], "maxResults": 15, "key": api_key},
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200:
        message = data.get("error", {}).get("message", resp.text[:300])
        raise RuntimeError(f"YouTube Data API error ({resp.status_code}): {message}")
    return parse_api(data)


def fetch_videos(channel_id: str, api_key: str | None = None) -> list[Video]:
    return fetch_api(channel_id, api_key) if api_key else fetch_feed(channel_id)


def is_short(video: Video) -> bool:
    # The feed links Shorts as /shorts/<id>. As a fallback, /shorts/<id> answers 200
    # for a Short and redirects to /watch for a regular video.
    if "/shorts/" in video.url:
        return True
    resp = requests.get(
        f"https://www.youtube.com/shorts/{video.id}",
        headers=HEADERS,
        allow_redirects=False,
        timeout=30,
    )
    return resp.status_code == 200
