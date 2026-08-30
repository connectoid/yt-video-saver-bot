from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.utils.url_utils import VIDEO_ID_RE

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

    known_language_users = stats.total_users - stats.unknown_language_users
    if known_language_users > 0:
        non_ru_percent = f"{stats.non_ru_users / known_language_users * 100:.0f}%"
    else:
        non_ru_percent = "—"

    lines = [
        "📊 <b>Статистика (текущие UTC-сутки)</b>",
        "",
        f"Всего пользователей: {stats.total_users}",
        f"Новых сегодня: {stats.new_users_today}",
        f"Активных сегодня: {stats.active_users_today}",
        f"Язык клиента не RU: {stats.non_ru_users} из {known_language_users} известных "
        f"({non_ru_percent}), неизвестно: {stats.unknown_language_users}",
        "",
        f"Скачано сегодня: {stats.downloads_success_today}",
        f"Скачано всего: {stats.downloads_success_total}",
        f"Заблокировано дневным лимитом сегодня: {stats.blocked_by_limit_today}",
        f"Заблокированное видео (запрошено) сегодня: {stats.blocked_video_today}",
        f"Отменено пользователями сегодня: {stats.cancelled_today}",
        f"Сообщений через /feedback сегодня: {stats.feedback_today}",
    ]

    if stats.failures_today_by_status:
        lines.append("")
        lines.append("Провалы сегодня по причинам:")
        for status, count in sorted(
            stats.failures_today_by_status.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"  • {status}: {count}")

    await message.answer("\n".join(lines))


@router.message(Command("block"))
async def cmd_block(
    message: Message, command: CommandObject, config: Config, db: Database | None = None
) -> None:
    """Добавить video_id в блок-лист: /block <video_id> [причина].

    Изменение применяется немедленно (следующий же запрос на это видео
    получит отказ — см. bot/handlers/video.py::_is_blocked_safe), без
    перезапуска бота — это и есть смысл держать блок-лист в БД, а не в
    конфиге: при реальной жалобе правообладателя счёт идёт на минуты."""
    user = message.from_user
    if user is None or not config.is_admin(user.id):
        return

    if db is None:
        await message.answer("⚠️ БД не инициализирована.")
        return

    args = (command.args or "").strip()
    if not args:
        await message.answer("Использование: /block <video_id> [причина]")
        return

    video_id, _, reason = args.partition(" ")
    reason = reason.strip() or None
    if not VIDEO_ID_RE.match(video_id):
        await message.answer(
            "⚠️ video_id должен быть 11 символов (буквы/цифры/-/_), как в "
            "ссылке YouTube — например, dQw4w9WgXcQ."
        )
        return

    await crud.block_video(db, video_id, reason=reason)
    reason_note = f" (причина: {reason})" if reason else ""
    await message.answer(f"🚫 Видео {video_id} добавлено в блок-лист{reason_note}.")


@router.message(Command("unblock"))
async def cmd_unblock(
    message: Message, command: CommandObject, config: Config, db: Database | None = None
) -> None:
    """Убрать video_id из блок-листа: /unblock <video_id>."""
    user = message.from_user
    if user is None or not config.is_admin(user.id):
        return

    if db is None:
        await message.answer("⚠️ БД не инициализирована.")
        return

    video_id = (command.args or "").strip().split(maxsplit=1)[:1]
    video_id = video_id[0] if video_id else ""
    if not video_id:
        await message.answer("Использование: /unblock <video_id>")
        return

    removed = await crud.unblock_video(db, video_id)
    if removed:
        await message.answer(f"✅ Видео {video_id} убрано из блок-листа.")
    else:
        await message.answer(f"Видео {video_id} и так не было в блок-листе.")


@router.message(Command("blocklist"))
async def cmd_blocklist(message: Message, config: Config, db: Database | None = None) -> None:
    """Показать текущий блок-лист: /blocklist."""
    user = message.from_user
    if user is None or not config.is_admin(user.id):
        return

    if db is None:
        await message.answer("⚠️ БД не инициализирована.")
        return

    entries = await crud.list_blocked_videos(db)
    if not entries:
        await message.answer("Блок-лист пуст.")
        return

    lines = ["🚫 Блок-лист видео:", ""]
    for entry in entries:
        reason_note = f" — {entry.reason}" if entry.reason else ""
        lines.append(f"• {entry.video_id}{reason_note} ({entry.blocked_at.strftime('%d.%m.%Y')})")
    await message.answer("\n".join(lines))
