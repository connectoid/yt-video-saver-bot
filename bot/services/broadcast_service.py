from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot

from bot.db import crud
from bot.db.engine import Database
from bot.i18n import resolve_language

logger = logging.getLogger(__name__)

# Telegram допускает ~30 сообщений/сек суммарно по разным чатам. 0.05с
# между отправками — это ~20/сек, с запасом ниже лимита (другие части бота
# тоже дёргают Bot API параллельно, например прогресс скачиваний).
SEND_INTERVAL_SECONDS = 0.05


@dataclass
class BroadcastResult:
    total: int
    sent: int
    failed: int


async def send_broadcast(bot: Bot, db: Database, ru_text: str, en_text: str) -> BroadcastResult:
    """Разослать ru_text/en_text всем пользователям из БД, каждому — на его
    эффективном языке (bot/i18n.py::resolve_language, та же логика, что и
    везде в боте: сохранённый выбор через /language приоритетнее языка
    клиента Telegram).

    Ошибки на отдельных получателях (бот заблокирован, чат удалён и т.п.)
    не прерывают рассылку — считаются в failed и логируются, остальные
    получатели всё равно получают сообщение. Синхронная задержка между
    отправками — намеренно простой троттлинг без внешних зависимостей,
    этого достаточно для объёма пользователей этого бота."""
    users = await crud.list_users_for_broadcast(db)
    result = BroadcastResult(total=len(users), sent=0, failed=0)

    for user_id, language_code, ui_language in users:
        lang = resolve_language(language_code, ui_language)
        text = ru_text if lang == "ru" else en_text
        try:
            await bot.send_message(user_id, text)
            result.sent += 1
        except Exception:
            result.failed += 1
            logger.info("Failed to deliver broadcast to user %s", user_id, exc_info=True)
        await asyncio.sleep(SEND_INTERVAL_SECONDS)

    return result
