from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.db import crud
from bot.db.engine import Database

logger = logging.getLogger(__name__)


class UserActivityMiddleware(BaseMiddleware):
    """Апсертит пользователя (first_seen/last_seen) на каждое сообщение и
    нажатие кнопки. Регистрируется как outer middleware на уровне
    Dispatcher для message и callback_query — так статистика "всего
    пользователей"/"активных сегодня" (см. /stats) не зависит от того,
    нашёлся ли в итоге подходящий обработчик.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db: Database | None = data.get("db")
        user = getattr(event, "from_user", None)
        if db is not None and user is not None and not user.is_bot:
            try:
                await crud.get_or_create_user(
                    db, user.id, user.username, user.full_name, user.language_code
                )
            except Exception:
                logger.exception("Failed to upsert user %s", user.id)
        return await handler(event, data)
