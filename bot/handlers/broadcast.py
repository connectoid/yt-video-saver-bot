from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import Config
from bot.db.engine import Database
from bot.services.broadcast_service import send_broadcast

logger = logging.getLogger(__name__)

router = Router(name="broadcast")


class BroadcastStates(StatesGroup):
    """Три состояния, а не два (waiting_for_ru -> waiting_for_en ->
    confirming), намеренно: FSMContext.clear() стирает не только текущее
    состояние, но и всё, что положено через update_data() (см. докстринг
    FeedbackStates в bot/handlers/feedback.py про то же поведение). Если бы
    после ввода английского текста мы сразу очищали состояние, введённые
    ru/en тексты потерялись бы раньше, чем админ успел бы их подтвердить —
    поэтому после ввода обоих текстов состояние переводится в отдельное
    confirming, а clear() вызывается только в handle_broadcast_confirm/
    handle_broadcast_cancel, уже после того как тексты прочитаны."""

    waiting_for_ru = State()
    waiting_for_en = State()
    confirming = State()


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Публичная (без подчёркивания) — используется не только внутри этого
    модуля, но и из bot/middlewares/broadcast_capture.py, которая
    показывает превью текста с этой клавиатурой сразу после ввода
    английского текста."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast:confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
            ]
        ]
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext, config: Config) -> None:
    """/broadcast — только для админов (см. config.admin_user_ids). Текст
    рассылки вводится в двух сообщениях подряд (RU, потом EN) — перехват
    этих сообщений реализован в
    bot/middlewares/broadcast_capture.py::BroadcastCaptureMiddleware, по
    той же схеме, что и /feedback (bot/middlewares/feedback_capture.py).

    Команда намеренно НЕ добавлена в bot/commands.py (ни в меню "/", ни в
    ADMIN_COMMANDS) — по аналогии с /block, /unblock, /blocklist, которые
    там тоже отсутствуют: нужна редко, вводится вручную."""
    user = message.from_user
    if user is None or not config.is_admin(user.id):
        return

    await state.set_state(BroadcastStates.waiting_for_ru)
    await message.answer(
        "📢 Рассылка информационного сообщения всем пользователям.\n\n"
        "Пришлите текст на русском (уйдёт пользователям с русским "
        "интерфейсом). Поддерживается форматирование Telegram (жирный, "
        "курсив, ссылки и т.п.). Для отмены — /cancel."
    )


@router.callback_query(F.data == "broadcast:confirm")
async def handle_broadcast_confirm(
    callback: CallbackQuery, state: FSMContext, config: Config, db: Database | None = None
) -> None:
    user = callback.from_user
    if user is None or not config.is_admin(user.id):
        await callback.answer()
        return

    current_state = await state.get_state()
    if current_state != BroadcastStates.confirming.state:
        await callback.answer("Уже неактуально.", show_alert=False)
        return

    data = await state.get_data()
    ru_text = data.get("broadcast_ru")
    en_text = data.get("broadcast_en")
    await state.clear()

    if not ru_text or not en_text or db is None:
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_text("⚠️ Не удалось запустить рассылку — данные потеряны.")
        return

    await callback.answer("Рассылка запущена")
    if isinstance(callback.message, Message):
        await callback.message.edit_text("🚀 Рассылка запущена, отчёт пришлю по завершении.")

    asyncio.create_task(_run_broadcast(callback.bot, db, ru_text, en_text, user.id))


@router.callback_query(F.data == "broadcast:cancel")
async def handle_broadcast_cancel(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    user = callback.from_user
    if user is None or not config.is_admin(user.id):
        await callback.answer()
        return

    await state.clear()
    await callback.answer("Отменено")
    if isinstance(callback.message, Message):
        await callback.message.edit_text("❌ Рассылка отменена, ничего не отправлено.")


async def _run_broadcast(bot: Bot, db: Database, ru_text: str, en_text: str, admin_id: int) -> None:
    """Сама отправка идёт в фоне (asyncio.create_task в
    handle_broadcast_confirm), а не внутри обработчика колбэка — рассылка
    на сколько-нибудь заметное число пользователей (с троттлингом ~20
    сообщений/сек, см. bot/services/broadcast_service.py) может занять
    минуты, и держать это время диспетчер aiogram заблокированным на одном
    update — плохая идея."""
    try:
        result = await send_broadcast(bot, db, ru_text, en_text)
    except Exception:
        logger.exception("Broadcast failed")
        try:
            await bot.send_message(admin_id, "⚠️ Рассылка прервалась ошибкой, см. логи.")
        except Exception:
            logger.exception("Failed to notify admin %s about broadcast failure", admin_id)
        return

    try:
        await bot.send_message(
            admin_id,
            f"✅ Рассылка завершена: {result.sent} из {result.total} доставлено"
            f"{f', ошибок: {result.failed}' if result.failed else ''}.",
        )
    except Exception:
        logger.exception("Failed to notify admin %s about broadcast result", admin_id)
