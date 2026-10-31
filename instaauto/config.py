import os
from dataclasses import dataclass

from .drive import folder_id_from

DEFAULT_CAPTION = "{caption}"


@dataclass(frozen=True)
class Config:
    drive_folder_id: str
    drive_credentials: str | None
    ig_token: str | None
    caption_template: str
    state_file: str
    graph_version: str
    dry_run: bool
    max_attempts: int
    max_posts_per_run: int
    min_age_minutes: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            drive_folder_id=folder_id_from(os.environ.get("GDRIVE_FOLDER_ID", "")),
            drive_credentials=os.environ.get("GDRIVE_SERVICE_ACCOUNT", "").strip() or None,
            ig_token=os.environ.get("IG_ACCESS_TOKEN", "").strip() or None,
            caption_template=os.environ.get("CAPTION_TEMPLATE") or DEFAULT_CAPTION,
            state_file=os.environ.get("STATE_FILE") or "state.json",
            graph_version=os.environ.get("GRAPH_API_VERSION") or "v23.0",
            dry_run=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"),
            max_attempts=int(os.environ.get("MAX_ATTEMPTS") or 5),
            max_posts_per_run=int(os.environ.get("MAX_POSTS_PER_RUN") or 1),
            min_age_minutes=int(os.environ.get("MIN_AGE_MINUTES") or 5),
        )
