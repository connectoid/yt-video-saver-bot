from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

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


FEEDBACK_PROMPT = (
    "✍️ Напишите одним сообщением, что хотите передать администратору. Подойдёт:\n\n"
    "• пожелание — какую функцию добавить;\n"
    "• проблема или ошибка в работе бота;\n"
    "• жалоба.\n\n"
    "Можно приложить скриншот. Следующее сообщение, которое вы отправите, "
    "уйдёт администратору напрямую — если передумали, отправьте /cancel."
)


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext) -> None:
    await state.set_state(FeedbackStates.waiting_for_message)
    await message.answer(FEEDBACK_PROMPT)
