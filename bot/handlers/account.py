from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.utils.formatting import format_history_entry

router = Router(name="account")

HISTORY_LIMIT = 10


@router.message(Command("limits"))
async def cmd_limits(message: Message, config: Config, db: Database | None = None) -> None:
    user = message.from_user
    if user is None:
        return

    if config.is_admin(user.id):
        await message.answer(
            "♾️ Вы админ — дневной лимит скачиваний на вас не действует."
        )
        return

    if db is None:
        await message.answer("⚠️ БД сейчас недоступна, лимит проверить не получится.")
        return

    used = await crud.count_successful_downloads_today(db, user.id)
    remaining = max(0, config.daily_download_limit - used)
    await message.answer(
        f"📊 Сегодня скачано: {used} из {config.daily_download_limit}.\n"
        f"Осталось: {remaining}.\n"
        "Лимит обнуляется в полночь по UTC."
    )


@router.message(Command("history"))
async def cmd_history(message: Message, db: Database | None = None) -> None:
    user = message.from_user
    if user is None:
        return

    if db is None:
        await message.answer("⚠️ БД сейчас недоступна, история недоступна.")
        return

    entries = await crud.get_recent_downloads(db, user.id, limit=HISTORY_LIMIT)
    if not entries:
        await message.answer("Пока нет ни одного скачанного видео.")
        return

    lines = [f"🗂 Последние скачивания (до {HISTORY_LIMIT}):", ""]
    for entry in entries:
        lines.append(
            format_history_entry(
                title=entry.title,
                video_id=entry.video_id,
                height=entry.height,
                file_size_bytes=entry.file_size_bytes,
                created_at=entry.created_at,
            )
        )
    await message.answer("\n".join(lines), disable_web_page_preview=True)
