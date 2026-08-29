from __future__ import annotations

import logging
from html import escape
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.db.models import EventStatus, Stage
from bot.handlers.feedback import FeedbackStates

logger = logging.getLogger(__name__)


async def _notify_admins(event: Message, config: Config) -> None:
    """Пересылает сообщение всем ADMIN_USER_IDS через message.forward(), а
    не пересборкой текста — так под /feedback подходит любой тип
    сообщения (текст, фото со скриншотом, документ), админ видит его как
    есть, и forward-заголовок Telegram обычно даёт кликабельную ссылку на
    отправителя. tg://user?id=... в префиксе — подстраховка на случай,
    если у пользователя в настройках приватности скрыт "Forwarded from"."""
    user = event.from_user
    if user is None:
        return
    label = f"@{user.username}" if user.username else (user.full_name or "пользователь")
    mention = f'<a href="tg://user?id={user.id}">{escape(label)}</a>'
    prefix = f"📬 Новое сообщение через /feedback от {mention} (id {user.id}):"
    for admin_id in config.admin_user_ids:
        try:
            await event.bot.send_message(admin_id, prefix)
            await event.forward(admin_id)
        except Exception:
            logger.exception("Failed to forward feedback to admin %s", admin_id)


class FeedbackCaptureMiddleware(BaseMiddleware):
    """Перехватывает РОВНО ОДНО следующее сообщение пользователя после
    /feedback (bot/handlers/feedback.py) и пересылает его всем
    ADMIN_USER_IDS, не давая ему дойти до обычных обработчиков (ссылка на
    YouTube, catch-all и т.д.).

    Регистрируется как dp.message.outer_middleware ПОСЛЕ
    UserActivityMiddleware (см. bot/main.py) — чтобы апсерт пользователя
    (first_seen/last_seen) всё равно отрабатывал для сообщений, которые
    тут же перехватываются и не доходят до роутеров.

    Состояние — разовое (см. FeedbackStates): сбрасывается сразу после
    первого же сообщения любого типа, ИЛИ сразу же, если это оказалась
    команда (текст, начинающийся с "/") — тогда состояние просто
    сбрасывается, а сама команда обрабатывается как обычно (ничего никуда
    не улетает). Реализовано middleware, а не StateFilter-хендлером в
    роутере: так порядок регистрации роутеров/хендлеров не влияет на то,
    что "выигрывает" — команда или перехват фидбека, и не нужно вручную
    прокидывать SkipHandler, чтобы после сброса состояния дать команде
    отработать штатно.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        state: FSMContext | None = data.get("state")
        if state is None:
            return await handler(event, data)

        current_state = await state.get_state()
        if current_state != FeedbackStates.waiting_for_message.state:
            return await handler(event, data)

        if event.text and event.text.startswith("/"):
            await state.clear()
            return await handler(event, data)

        await state.clear()

        config: Config | None = data.get("config")
        if config is None or not config.admin_user_ids:
            await event.answer("⚠️ Не удалось отправить — администратор не настроен.")
            return None

        await _notify_admins(event, config)
        await event.answer("✅ Спасибо! Сообщение отправлено администратору.")

        db: Database | None = data.get("db")
        user = event.from_user
        if db is not None and user is not None:
            try:
                await crud.log_event(
                    db, user_id=user.id, stage=Stage.FEEDBACK, status=EventStatus.SUCCESS
                )
            except Exception:
                logger.exception("Failed to log feedback event for user %s", user.id)

        return None
