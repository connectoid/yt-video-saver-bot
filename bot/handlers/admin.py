from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database

logger = logging.getLogger(__name__)

router = Router(name="admin")


@router.message(Command("stats"))
async def cmd_stats(message: Message, config: Config, db: Database | None = None) -> None:
    user = message.from_user
    if user is None or not config.is_admin(user.id):
        # Молча игнорируем — не подтверждаем не-админам, что команда вообще
        # существует.
        return

    if db is None:
        await message.answer("⚠️ БД не инициализирована.")
        return

    stats = await crud.get_stats(db)

    lines = [
        "📊 <b>Статистика (текущие UTC-сутки)</b>",
        "",
        f"Всего пользователей: {stats.total_users}",
        f"Новых сегодня: {stats.new_users_today}",
        f"Активных сегодня: {stats.active_users_today}",
        "",
        f"Скачано сегодня: {stats.downloads_success_today}",
        f"Скачано всего: {stats.downloads_success_total}",
        f"Заблокировано дневным лимитом сегодня: {stats.blocked_by_limit_today}",
    ]

    if stats.failures_today_by_status:
        lines.append("")
        lines.append("Провалы сегодня по причинам:")
        for status, count in sorted(
            stats.failures_today_by_status.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"  • {status}: {count}")

    await message.answer("\n".join(lines))
