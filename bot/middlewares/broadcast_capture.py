from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from bot.config import Config
from bot.handlers.broadcast import BroadcastStates, confirm_keyboard

logger = logging.getLogger(__name__)


class BroadcastCaptureMiddleware(BaseMiddleware):
    """Перехватывает два сообщения подряд после /broadcast
    (bot/handlers/broadcast.py) — сначала русский текст рассылки, потом
    английский — и не даёт им дойти до обычных обработчиков. Структура
    один в один повторяет FeedbackCaptureMiddleware
    (bot/middlewares/feedback_capture.py, см. его докстринг за подробным
    обоснованием middleware вместо StateFilter-хендлера в роутере).

    Регистрируется как dp.message.outer_middleware ПОСЛЕ
    UserActivityMiddleware, рядом с FeedbackCaptureMiddleware (см.
    bot/main.py).

    Захватываем event.html_text, а не event.text — так сохраняется
    Telegram-разметка (жирный, курсив, ссылки), которую админ применил при
    наборе текста рассылки, и она же корректно экранируется под
    ParseMode.HTML бота (DefaultBotProperties в bot/main.py), которым эти
    тексты потом рассылаются как есть через bot.send_message.

    Если вместо текста рассылки приходит команда ("/..."), состояние
    сбрасывается и команда обрабатывается как обычно — как и в
    FeedbackCaptureMiddleware, это значит, что /cancel в такой момент
    попадёт в bot/handlers/video.py::cmd_cancel и ответит "нечего
    отменять" (состояние уже сброшено этой же веткой) — тот же
    сознательно принятый компромисс, что и в фидбеке, отдельно не
    чинится."""

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
        if current_state not in (
            BroadcastStates.waiting_for_ru.state,
            BroadcastStates.waiting_for_en.state,
        ):
            return await handler(event, data)

        config: Config | None = data.get("config")
        user = event.from_user
        if config is None or user is None or not config.is_admin(user.id):
            await state.clear()
            return await handler(event, data)

        if event.text and event.text.startswith("/"):
            await state.clear()
            return await handler(event, data)

        text = (event.html_text or "").strip()
        if not text:
            await event.answer("Пустое сообщение не подходит, пришлите текст ещё раз.")
            return None

        if current_state == BroadcastStates.waiting_for_ru.state:
            await state.update_data(broadcast_ru=text)
            await state.set_state(BroadcastStates.waiting_for_en)
            await event.answer(
                "Принято. Теперь пришлите текст на английском (уйдёт "
                "остальным пользователям)."
            )
            return None

        # waiting_for_en
        await state.update_data(broadcast_en=text)
        await state.set_state(BroadcastStates.confirming)
        stored = await state.get_data()
        preview = (
            "Проверьте текст перед отправкой:\n\n"
            f"<b>RU:</b>\n{stored.get('broadcast_ru', '')}\n\n"
            f"<b>EN:</b>\n{text}"
        )
        await event.answer(preview, reply_markup=confirm_keyboard())
        return None
