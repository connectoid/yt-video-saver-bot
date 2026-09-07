from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.db import crud
from bot.db.engine import Database
from bot.i18n import resolve_language

logger = logging.getLogger(__name__)


class UserActivityMiddleware(BaseMiddleware):
    """Апсертит пользователя (first_seen/last_seen) на каждое сообщение и
    нажатие кнопки, и кладёт в data["lang"] эффективный язык интерфейса
    (см. bot/i18n.py::resolve_language) — единственное место, где он
    вычисляется. Регистрируется как outer middleware на уровне Dispatcher
    для message и callback_query (см. bot/main.py) — так и апсерт, и lang
    доступны каждому хендлеру/middleware ниже по цепочке независимо от
    того, нашёлся ли в итоге подходящий обработчик (aiogram передаёт data
    дальше по имени параметра — хендлер получает lang: str автоматически).

    data["lang"] выставляется ВСЕГДА (даже без user/db) — DEFAULT_LANGUAGE
    как последний фолбэк, чтобы data.get("lang") у нижестоящего кода не
    нужен был вовсе, можно просто требовать параметр lang.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db: Database | None = data.get("db")
        user = getattr(event, "from_user", None)

        lang = resolve_language(None, None)
        if user is not None and not user.is_bot:
            # Базовая оценка по одному только языку клиента Telegram —
            # работает даже если апсерт в БД ниже не удастся (see except).
            lang = resolve_language(user.language_code, None)
            if db is not None:
                try:
                    db_user = await crud.get_or_create_user(
                        db, user.id, user.username, user.full_name, user.language_code
                    )
                    lang = resolve_language(user.language_code, db_user.ui_language)
                except Exception:
                    logger.exception("Failed to upsert user %s", user.id)

        data["lang"] = lang
        return await handler(event, data)
