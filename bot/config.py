from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    """Прочитать переменную окружения, подставив default и когда она вовсе
    не задана, и когда задана пустой строкой.

    os.getenv(name, default) подставляет default только в первом случае —
    "VAR=" в .env (переменная присутствует, но пустая) читается как "" и
    default НЕ применяется. Именно это уронило бота: DATABASE_URL= в .env
    задумывался как "использовать путь по умолчанию", а получил пустую
    строку, которую SQLAlchemy не смогла распарсить как URL.
    """
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError:
            continue
    return frozenset(ids)


@dataclass(frozen=True)
class Config:
    bot_token: str
    max_concurrent_downloads: int
    downloads_dir: Path
    log_level: str
    max_file_size_mb: int
    database_url: str
    daily_download_limit: int
    admin_user_ids: frozenset[int] = field(default_factory=frozenset)
    telegram_api_base_url: str | None = None

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids


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

    downloads_dir = BASE_DIR / _env("DOWNLOADS_DIR", "downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)

    default_db_path = BASE_DIR / "bot.db"
    database_url = _env("DATABASE_URL", f"sqlite+aiosqlite:///{default_db_path}")

    telegram_api_base_url = _env("TELEGRAM_API_BASE_URL", "") or None

    return Config(
        bot_token=bot_token,
        max_concurrent_downloads=int(_env("MAX_CONCURRENT_DOWNLOADS", "3")),
        downloads_dir=downloads_dir,
        log_level=_env("LOG_LEVEL", "INFO").upper(),
        max_file_size_mb=int(_env("MAX_FILE_SIZE_MB", "50")),
        database_url=database_url,
        daily_download_limit=int(_env("DAILY_DOWNLOAD_LIMIT", "5")),
        admin_user_ids=_parse_admin_ids(_env("ADMIN_USER_IDS", "")),
        telegram_api_base_url=telegram_api_base_url,
    )
