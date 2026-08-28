from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    max_concurrent_downloads: int
    downloads_dir: Path
    log_level: str
    max_file_size_mb: int

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def load_config(env_file: str | Path | None = None) -> Config:
    """Load configuration from environment variables / a .env file.

    Raises RuntimeError if BOT_TOKEN is missing, so the bot fails fast on
    startup instead of crashing later on the first incoming message.
    """
    load_dotenv(env_file or BASE_DIR / ".env")

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен."
        )

    downloads_dir = BASE_DIR / os.getenv("DOWNLOADS_DIR", "downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=bot_token,
        max_concurrent_downloads=int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3")),
        downloads_dir=downloads_dir,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "50")),
    )
