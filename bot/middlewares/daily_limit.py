from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.db.models import EventStatus, Stage

logger = logging.getLogger(__name__)


class DailyLimitMiddleware(BaseMiddleware):
    """Блокирует старт скачивания, если пользователь уже исчерпал дневной
    лимит успешных загрузок за текущие UTC-сутки.

    Регистрируется на callback_query роутера video (см. bot/handlers/video.py)
    — то есть срабатывает до вызова handle_resolution_choice. Каждая
    блокировка тоже логируется как событие (EventStatus.BLOCKED_DAILY_LIMIT),
    чтобы в /stats было видно, сколько пользователей реально упираются в
    лимит — это прямой сигнал платёжеспособного спроса на будущий платный
    тариф без лимита.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery) or event.data is None:
            return await handler(event, data)
        if not event.data.startswith("dl:"):
            return await handler(event, data)

        db: Database | None = data.get("db")
        config: Config | None = data.get("config")
        if db is None or config is None:
            return await handler(event, data)

        user_id = event.from_user.id
        if config.is_admin(user_id):
            # Админы (ADMIN_USER_IDS) не ограничены дневным лимитом — им
            # нужно свободно тестировать бота без ожидания сброса в полночь.
            return await handler(event, data)

        used = await crud.count_successful_downloads_today(db, user_id)
        if used < config.daily_download_limit:
            return await handler(event, data)

        logger.info("User %s hit daily download limit (%s)", user_id, config.daily_download_limit)
        try:
            await crud.log_event(
                db,
                user_id=user_id,
                stage=Stage.DOWNLOAD,
                status=EventStatus.BLOCKED_DAILY_LIMIT,
            )
        except Exception:
            logger.exception("Failed to log blocked_daily_limit event for user %s", user_id)

        await event.answer(
            f"⚠️ Дневной лимит скачиваний исчерпан ({config.daily_download_limit} в сутки). "
            "Попробуйте снова после полуночи по UTC.",
            show_alert=True,
        )
        return None
