from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.i18n import TRANSLATIONS, t

router = Router(name="feedback")


class FeedbackStates(StatesGroup):
    """Единственное состояние: бот ждёт следующее сообщение пользователя,
    чтобы переслать его администратору. Разовое, а не "сессия" — см.
    bot/middlewares/feedback_capture.py: состояние сбрасывается сразу
    после первого же полученного сообщения (или команды), а не держится
    до явной отмены. Иначе ссылка на видео, отправленная значительно
    позже (пользователь просто забыл, что недавно вызывал /feedback),
    могла бы случайно улететь администратору вместо обычной обработки.
    """

    waiting_for_message = State()


# Оставлено как алиас на русский текст ради обратной совместимости (тесты и
# любой внешний код, который мог на него ссылаться до локализации) — сам
# хендлер ниже берёт текст через t(lang, "feedback_prompt"), эта константа
# больше не участвует в реальной отправке.
FEEDBACK_PROMPT = TRANSLATIONS["ru"]["feedback_prompt"]


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(FeedbackStates.waiting_for_message)
    await message.answer(t(lang, "feedback_prompt"))
