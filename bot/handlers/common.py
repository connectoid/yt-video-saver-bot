from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="common")

WELCOME_TEXT = (
    "👋 Привет! Я скачиваю видео и Shorts с YouTube.\n\n"
    "Просто пришли мне ссылку на видео — я покажу превью и предложу "
    "доступные разрешения для скачивания."
)

HELP_TEXT = (
    "Как пользоваться:\n"
    "1. Отправь ссылку на видео или Shorts с YouTube.\n"
    "2. Выбери разрешение из предложенных кнопок.\n"
    "3. Дождись, пока я скачаю и пришлю файл.\n\n"
    "Команды:\n"
    "/limits — сколько скачиваний осталось сегодня\n"
    "/history — последние скачанные видео\n"
    "/cancel — отменить текущее скачивание\n\n"
    "⚠️ Пока действует ограничение Telegram: боты не могут отправлять "
    "файлы крупнее 50 МБ. Обход этого лимита в разработке."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
