import os
from dataclasses import dataclass

DEFAULT_CAPTION = "{title}\n\n{description}"


@dataclass(frozen=True)
class Config:
    channel_id: str
    yt_api_key: str | None
    ig_token: str | None
    yt_cookies: str | None
    caption_template: str
    state_file: str
    graph_version: str
    dry_run: bool
    max_attempts: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            channel_id=os.environ.get("YT_CHANNEL_ID", "").strip(),
            yt_api_key=os.environ.get("YT_API_KEY", "").strip() or None,
            ig_token=os.environ.get("IG_ACCESS_TOKEN", "").strip() or None,
            yt_cookies=os.environ.get("YT_COOKIES") or None,
            caption_template=os.environ.get("CAPTION_TEMPLATE") or DEFAULT_CAPTION,
            state_file=os.environ.get("STATE_FILE") or "state.json",
            graph_version=os.environ.get("GRAPH_API_VERSION") or "v23.0",
            dry_run=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"),
            max_attempts=int(os.environ.get("MAX_ATTEMPTS") or 5),
        )
