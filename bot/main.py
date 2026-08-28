from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.handlers import get_root_router
from bot.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    setup_logging(config.log_level)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(get_root_router())

    # Общий семафор ограничивает число одновременных скачиваний yt-dlp,
    # чтобы не положить сервер при наплыве пользователей.
    semaphore = asyncio.Semaphore(config.max_concurrent_downloads)

    logger.info(
        "Starting bot (max_concurrent_downloads=%s, max_file_size_mb=%s)",
        config.max_concurrent_downloads,
        config.max_file_size_mb,
    )

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        # config/semaphore передаются как extra kwargs в start_polling —
        # aiogram сам прокинет их в обработчики по имени параметра.
        await dp.start_polling(bot, config=config, semaphore=semaphore)
    finally:
        await bot.session.close()
