from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import Config
from bot.utils.formatting import build_terms_text, format_file_limit_note

router = Router(name="common")

WELCOME_TEXT = (
    "👋 Привет! Я скачиваю видео и Shorts с YouTube.\n\n"
    "Просто пришли мне ссылку на видео — я покажу превью и предложу "
    "доступные разрешения для скачивания.\n\n"
    "Скачивая видео, вы соглашаетесь с условиями использования — /terms."
)

HELP_TEXT_HEADER = (
    "Как пользоваться:\n"
    "1. Отправь ссылку на видео или Shorts с YouTube.\n"
    "2. Выбери разрешение из предложенных кнопок.\n"
    "3. Дождись, пока я скачаю и пришлю файл.\n\n"
    "Команды:\n"
    "/limits — сколько скачиваний осталось сегодня\n"
    "/history — последние скачанные видео\n"
    "/cancel — отменить текущее скачивание\n"
    "/terms — условия использования\n"
    "/feedback — написать администратору (пожелание, баг, жалоба)\n\n"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message, config: Config) -> None:
    await message.answer(HELP_TEXT_HEADER + format_file_limit_note(config))


@router.message(Command("terms"))
async def cmd_terms(message: Message, config: Config) -> None:
    await message.answer(build_terms_text(config.support_contact))
