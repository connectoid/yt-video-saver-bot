from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat

from bot.config import Config

logger = logging.getLogger(__name__)

# Команды, которые видны всем пользователям в меню бота (иконка "/" рядом
# с полем ввода в Telegram). /stats, /block, /unblock, /blocklist сюда
# намеренно не входят — это админ-команды, admin.py молча их игнорирует
# для не-админов, чтобы не выдавать сам факт их существования; попадание
# в публичное меню это бы перечеркнуло.
PUBLIC_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Начать работу с ботом"),
    BotCommand(command="help", description="Как пользоваться ботом"),
    BotCommand(command="limits", description="Сколько скачиваний осталось сегодня"),
    BotCommand(command="history", description="Последние скачанные видео"),
    BotCommand(command="cancel", description="Отменить текущее скачивание"),
    BotCommand(command="terms", description="Условия использования"),
    BotCommand(command="feedback", description="Написать администратору"),
]

# Меню для админов: то же самое + /stats. Не отдельный список с нуля, а
# PUBLIC_COMMANDS + одна команда — так он не может незаметно разойтись с
# публичным меню, если кто-то потом добавит/уберёт команду в одном месте
# и забудет про другое.
ADMIN_COMMANDS: list[BotCommand] = [
    *PUBLIC_COMMANDS,
    BotCommand(command="stats", description="Статистика бота"),
]


async def set_bot_commands(bot: Bot, config: Config) -> None:
    # Дефолтный скоуп (BotCommandScopeDefault) — меню для всех, у кого нет
    # более специфичного скоупа. /block, /unblock, /blocklist сюда не
    # добавлены — они реже нужны админу "на лету", чем /stats, и пока не
    # запрашивались; их можно добавить в ADMIN_COMMANDS так же, если понадобится.
    await bot.set_my_commands(PUBLIC_COMMANDS)

    for admin_id in config.admin_user_ids:
        # BotCommandScopeChat персонально на chat_id админа — Telegram
        # показывает такой список ВМЕСТО дефолтного именно в этом чате, у
        # всех остальных пользователей остаётся PUBLIC_COMMANDS. Telegram
        # отвечает "chat not found", если бот с этим chat_id ещё ни разу не
        # переписывался (админ ещё не нажал /start) — это не баг конфига,
        # просто нечего обновлять, пока переписки нет; поэтому каждый
        # админ — в своём try/except, чтобы такой случай не мешал ни
        # остальным админам, ни самому запуску бота.
        try:
            await bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except TelegramBadRequest:
            logger.warning(
                "Не удалось задать админ-меню для %s (вероятно, ещё не "
                "писал боту) — применится при следующем перезапуске после "
                "первого /start.",
                admin_id,
            )
