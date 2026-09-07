from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.i18n import t
from bot.utils.formatting import format_history_entry

router = Router(name="account")

HISTORY_LIMIT = 10


@router.message(Command("limits"))
async def cmd_limits(
    message: Message, config: Config, lang: str, db: Database | None = None
) -> None:
    user = message.from_user
    if user is None:
        return

    if config.is_admin(user.id):
        await message.answer(t(lang, "limits_admin_unlimited"))
        return

    if db is None:
        await message.answer(t(lang, "limits_db_unavailable"))
        return

    used = await crud.count_successful_downloads_today(db, user.id)
    remaining = max(0, config.daily_download_limit - used)
    await message.answer(
        t(lang, "limits_summary", used=used, limit=config.daily_download_limit, remaining=remaining)
    )


@router.message(Command("history"))
async def cmd_history(message: Message, lang: str, db: Database | None = None) -> None:
    user = message.from_user
    if user is None:
        return

    if db is None:
        await message.answer(t(lang, "history_db_unavailable"))
        return

    entries = await crud.get_recent_downloads(db, user.id, limit=HISTORY_LIMIT)
    if not entries:
        await message.answer(t(lang, "history_empty"))
        return

    lines = [t(lang, "history_header", limit=HISTORY_LIMIT), ""]
    for entry in entries:
        lines.append(
            format_history_entry(
                title=entry.title,
                video_id=entry.video_id,
                height=entry.height,
                file_size_bytes=entry.file_size_bytes,
                created_at=entry.created_at,
                lang=lang,
            )
        )
    await message.answer("\n".join(lines), disable_web_page_preview=True)
