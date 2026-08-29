from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand

# Команды, которые видны всем пользователям в меню бота (иконка "/" рядом
# с полем ввода в Telegram). /stats сюда намеренно не входит — это
# админ-команда, admin.py молча её игнорирует для не-админов, чтобы не
# выдавать сам факт её существования; попадание в публичное меню это бы
# перечеркнуло.
PUBLIC_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Начать работу с ботом"),
    BotCommand(command="help", description="Как пользоваться ботом"),
    BotCommand(command="limits", description="Сколько скачиваний осталось сегодня"),
    BotCommand(command="history", description="Последние скачанные видео"),
    BotCommand(command="cancel", description="Отменить текущее скачивание"),
]


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(PUBLIC_COMMANDS)
