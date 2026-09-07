from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import crud
from bot.db.engine import Database
from bot.i18n import SUPPORTED_LANGUAGES, t

logger = logging.getLogger(__name__)

router = Router(name="language")

# Подписи кнопок — намеренно НЕ через t()/текущий lang: показываем оба
# варианта сразу, каждый на своём языке, чтобы человек узнал нужную кнопку
# даже если сейчас видит интерфейс не на том языке, который хочет выбрать.
_LANGUAGE_LABELS: dict[str, str] = {"en": "English", "ru": "Русский"}


def _language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code in SUPPORTED_LANGUAGES:
        builder.button(text=_LANGUAGE_LABELS[code], callback_data=f"lang:{code}")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("language"))
async def cmd_language(message: Message, lang: str) -> None:
    await message.answer(t(lang, "language_prompt"), reply_markup=_language_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def handle_language_choice(callback: CallbackQuery, db: Database | None = None) -> None:
    assert callback.data is not None
    _, code = callback.data.split(":", 1)
    if code not in SUPPORTED_LANGUAGES:
        await callback.answer()
        return

    user_id = callback.from_user.id
    if db is not None:
        try:
            await crud.set_ui_language(db, user_id, code)
        except Exception:
            logger.exception("Failed to save ui_language for user %s", user_id)

    await callback.answer()
    text = t(code, "language_saved")
    if callback.message is not None:
        try:
            await callback.message.edit_text(text)
        except Exception:
            # Например, сообщение с кнопками уже удалено/слишком старое —
            # выбор языка при этом всё равно сохранён (см. set_ui_language
            # выше), просто подтверждение шлём новым сообщением.
            await callback.message.answer(text)
