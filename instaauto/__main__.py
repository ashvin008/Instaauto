"""Entry point.

  python -m instaauto check   find new Shorts on the channel and mark them pending
  python -m instaauto run     download each pending Short and post it as a Reel
  python -m instaauto whoami  check that the Instagram token works
"""

import os
import sys
from pathlib import Path

from . import state as st
from .config import Config
from .downloader import get_video
from .instagram import CAPTION_LIMIT, Instagram
from .youtube import fetch_videos, is_short

WORK_DIR = Path("tmp")


class _Blank(dict):
    def __missing__(self, key):
        return ""


def build_caption(template: str, entry: dict) -> str:
    caption = template.replace("\\n", "\n").format_map(_Blank(
        title=entry.get("title", ""),
        description=entry.get("description", ""),
        url=entry.get("url", ""),
    ))
    return caption.strip()[:CAPTION_LIMIT]


def set_output(name: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def pending_ids(state: dict, max_attempts: int) -> list[str]:
    items = [
        (vid, e) for vid, e in state["videos"].items()
        if e["status"] == st.PENDING or (e["status"] == st.FAILED and e.get("attempts", 0) < max_attempts)
    ]
    return [vid for vid, e in sorted(items, key=lambda i: i[1].get("published", ""))]


def check(cfg: Config) -> int:
    if not cfg.channel_id:
        raise SystemExit("YT_CHANNEL_ID is not set (it looks like UCxxxxxxxxxxxxxxxxxxxxxx).")
    videos = fetch_videos(cfg.channel_id, cfg.yt_api_key)
    state = st.load(cfg.state_file)

    if state is None:
        # First run: don't repost the whole back catalogue, only uploads from now on.
        state = {"videos": {
            v.id: {"status": st.SKIPPED, "reason": "uploaded before setup", "title": v.title,
                   "published": v.published, "at": st.now()}
            for v in videos
        }}
        st.save(cfg.state_file, state)
        print(f"First run: remembered {len(videos)} existing videos. Only new Shorts will be posted.")
        set_output("pending", "false")
        return 0

    for v in videos:
        if v.id in state["videos"]:
            continue
        if is_short(v):
            print(f"New Short: {v.title} ({v.id})")
            state["videos"][v.id] = {
                "status": st.PENDING, "title": v.title, "description": v.description,
                "url": v.url, "published": v.published, "attempts": 0, "at": st.now(),
            }
        else:
            print(f"Skipping regular video: {v.title} ({v.id})")
            state["videos"][v.id] = {"status": st.SKIPPED, "reason": "not a Short", "title": v.title,
                                     "published": v.published, "at": st.now()}
    st.save(cfg.state_file, state)

    pending = pending_ids(state, cfg.max_attempts)
    print(f"{len(pending)} Short(s) waiting to be posted.")
    set_output("pending", "true" if pending else "false")
    return 0


def run(cfg: Config) -> int:
    state = st.load(cfg.state_file)
    if state is None:
        raise SystemExit("No state file yet. Run `python -m instaauto check` first.")
    pending = pending_ids(state, cfg.max_attempts)
    if not pending:
        print("Nothing to post.")
        return 0

    if cfg.dry_run:
        for vid in pending:
            caption = build_caption(cfg.caption_template, state["videos"][vid])
            print(f"[dry run] Would post {vid} as a Reel with caption:\n{caption}\n")
        return 0

    if not cfg.ig_token:
        raise SystemExit("IG_ACCESS_TOKEN is not set.")
    ig = Instagram(cfg.ig_token, cfg.graph_version)

    failures = 0
    for vid in pending:
        entry = state["videos"][vid]
        print(f"Posting {entry['title']} ({vid})")
        try:
            video = get_video(vid, WORK_DIR, cfg.yt_cookies)
            media_id = ig.publish_reel(video, build_caption(cfg.caption_template, entry))
        except Exception as e:  # keep going with the other Shorts, retry this one next run
            failures += 1
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["error"] = str(e)[:500]
            entry["status"] = st.GAVE_UP if entry["attempts"] >= cfg.max_attempts else st.FAILED
            print(f"::error::Could not post {vid} (attempt {entry['attempts']}/{cfg.max_attempts}): {e}")
        else:
            entry.update(status=st.POSTED, ig_media_id=media_id, posted_at=st.now())
            entry.pop("error", None)
            print(f"  Posted as Instagram media {media_id}")
        entry["at"] = st.now()
        # Save after every video so a crash later can never cause a double post.
        st.save(cfg.state_file, state)

    return 1 if failures else 0


def whoami(cfg: Config) -> int:
    if not cfg.ig_token:
        raise SystemExit("IG_ACCESS_TOKEN is not set.")
    me = Instagram(cfg.ig_token, cfg.graph_version).me()
    print(f"Token works for @{me.get('username')} (user_id {me.get('user_id')})")
    return 0


def main() -> int:
    commands = {"check": check, "run": run, "whoami": whoami}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        return 2
    return commands[sys.argv[1]](Config.from_env())


if __name__ == "__main__":
    sys.exit(main())
