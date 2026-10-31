"""Entry point.

  python -m instaauto check   find new videos in the Google Drive folder
  python -m instaauto run     post pending videos as Reels (MAX_POSTS_PER_RUN per run)
  python -m instaauto whoami  check that the Instagram token works
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import state as st
from .config import Config
from .drive import FAILED, POSTED, Drive
from .instagram import CAPTION_LIMIT, Instagram
from .media import ensure_instagram_compatible

WORK_DIR = Path("tmp")


class _Blank(dict):
    def __missing__(self, key):
        return ""


def build_caption(template: str, caption: str, filename: str) -> str:
    text = template.replace("\\n", "\n").format_map(_Blank(caption=caption, filename=filename))
    return text.strip()[:CAPTION_LIMIT]


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
    return [vid for vid, e in sorted(items, key=lambda i: i[1].get("created", ""))]


def is_too_new(created: str, min_age_minutes: int) -> bool:
    # Gives you a few minutes to also upload the caption .txt after the video.
    uploaded = datetime.fromisoformat(created.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - uploaded < timedelta(minutes=min_age_minutes)


def open_drive(cfg: Config) -> Drive:
    if not cfg.drive_folder_id:
        raise SystemExit("GDRIVE_FOLDER_ID is not set.")
    if not cfg.drive_credentials:
        raise SystemExit("GDRIVE_SERVICE_ACCOUNT is not set (paste the service account's JSON key).")
    return Drive(cfg.drive_credentials, cfg.drive_folder_id)


def check(cfg: Config) -> int:
    videos, _ = open_drive(cfg).list_folder()
    state = st.load(cfg.state_file) or {"videos": {}}

    for v in videos:
        if v["id"] in state["videos"]:
            continue
        if is_too_new(v["createdTime"], cfg.min_age_minutes):
            print(f"Waiting: {v['name']} was uploaded less than {cfg.min_age_minutes} min ago")
            continue
        print(f"New video: {v['name']}")
        state["videos"][v["id"]] = {
            "status": st.PENDING, "name": v["name"], "created": v["createdTime"], "attempts": 0, "at": st.now(),
        }
    st.save(cfg.state_file, state)

    pending = pending_ids(state, cfg.max_attempts)
    print(f"{len(pending)} video(s) waiting to be posted.")
    set_output("pending", "true" if pending else "false")
    return 0


def move_quietly(drive: Drive, file_id: str | None, subfolder: str) -> None:
    # Moving is only for tidiness; state.json is what prevents double posts.
    if not file_id:
        return
    try:
        drive.move(file_id, subfolder)
    except Exception as e:
        print(f"::warning::Could not move file to {subfolder}/: {e}")


def run(cfg: Config) -> int:
    state = st.load(cfg.state_file)
    pending = pending_ids(state, cfg.max_attempts) if state else []
    if not pending:
        print("Nothing to post.")
        return 0

    drive = open_drive(cfg)
    _, captions = drive.list_folder()
    if not cfg.dry_run and not cfg.ig_token:
        raise SystemExit("IG_ACCESS_TOKEN is not set.")
    ig = None if cfg.dry_run else Instagram(cfg.ig_token, cfg.graph_version)

    failures = 0
    for vid in pending[:cfg.max_posts_per_run]:
        entry = state["videos"][vid]
        name = entry["name"]
        caption_id = captions.get(Path(name).stem)
        text = drive.read_text(caption_id) if caption_id else Path(name).stem
        caption = build_caption(cfg.caption_template, text, name)

        if cfg.dry_run:
            print(f"[dry run] Would post {name} as a Reel with caption:\n{caption}\n")
            continue

        print(f"Posting {name}")
        try:
            video = drive.download(vid, WORK_DIR / f"{vid}{Path(name).suffix or '.mp4'}")
            media_id = ig.publish_reel(ensure_instagram_compatible(video), caption)
        except Exception as e:  # keep the state consistent and retry this one next run
            failures += 1
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["error"] = str(e)[:500]
            entry["status"] = st.GAVE_UP if entry["attempts"] >= cfg.max_attempts else st.FAILED
            print(f"::error::Could not post {name} (attempt {entry['attempts']}/{cfg.max_attempts}): {e}")
            if entry["status"] == st.GAVE_UP:
                move_quietly(drive, vid, FAILED)
                move_quietly(drive, caption_id, FAILED)
        else:
            entry.update(status=st.POSTED, ig_media_id=media_id, posted_at=st.now())
            entry.pop("error", None)
            print(f"  Posted as Instagram media {media_id}")
            move_quietly(drive, vid, POSTED)
            move_quietly(drive, caption_id, POSTED)
        entry["at"] = st.now()
        # Save after every video so a crash later can never cause a double post.
        st.save(cfg.state_file, state)

    left = len(pending) - cfg.max_posts_per_run
    if left > 0 and not cfg.dry_run:
        print(f"{left} more video(s) will be posted in the next runs.")
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
