"""Remembers which YouTube videos were already handled, so nothing is posted twice.

The file is committed back to the repo by the workflow after every run.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

PENDING = "pending"
POSTED = "posted"
FAILED = "failed"
GAVE_UP = "gave_up"
SKIPPED = "skipped"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(path: str, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
