from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from bot.commands import set_bot_commands
from bot.config import load_config
from bot.db.engine import Database
from bot.handlers import get_root_router
from bot.logging_config import setup_logging
from bot.middlewares.feedback_capture import FeedbackCaptureMiddleware
from bot.middlewares.user_activity import UserActivityMiddleware
from bot.profile import set_bot_profile

logger = logging.getLogger(__name__)


def _build_bot(token: str, api_base_url: str | None) -> Bot:
    session = None
    if api_base_url:
        # Локальный Bot API сервер (telegram-bot-api) поднимает лимит на
        # отправку файлов с 50 МБ до 2000 МБ. См. README и docker-compose.yml.
        session = AiohttpSession(api=TelegramAPIServer.from_base(api_base_url))
        logger.info("Using local Bot API server at %s", api_base_url)
    return Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def main() -> None:
    config = load_config()
    setup_logging(config.log_level)

    bot = _build_bot(config.bot_token, config.telegram_api_base_url)

    db = Database(config.database_url)
    await db.create_all()

    dp = Dispatcher()
    dp.include_router(get_root_router())

    # Апсерт пользователя (first_seen/last_seen) на каждое сообщение и
    # нажатие кнопки — outer middleware, чтобы срабатывать даже если ни
    # один обработчик в итоге не совпал.
    dp.message.outer_middleware(UserActivityMiddleware())
    dp.callback_query.outer_middleware(UserActivityMiddleware())

    # Перехват сообщения для /feedback — ПОСЛЕ UserActivityMiddleware (чтобы
    # апсерт пользователя всё равно отработал), но раньше роутеров: если
    # пользователь только что вызвал /feedback, следующее его сообщение
    # уходит администратору и не доходит до обычных обработчиков.
    dp.message.outer_middleware(FeedbackCaptureMiddleware())

    # Общий семафор ограничивает число одновременных скачиваний yt-dlp,
    # чтобы не положить сервер при наплыве пользователей.
    semaphore = asyncio.Semaphore(config.max_concurrent_downloads)

    logger.info(
        "Starting bot (max_concurrent_downloads=%s, max_file_size_mb=%s, "
        "daily_download_limit=%s, local_bot_api=%s)",
        config.max_concurrent_downloads,
        config.max_file_size_mb,
        config.daily_download_limit,
        bool(config.telegram_api_base_url),
    )

    await bot.delete_webhook(drop_pending_updates=True)
    await set_bot_commands(bot, config)
    await set_bot_profile(bot)
    try:
        # config/semaphore/db передаются как extra kwargs в start_polling —
        # aiogram сам прокинет их в обработчики и middleware по имени
        # параметра.
        await dp.start_polling(bot, config=config, semaphore=semaphore, db=db)
    finally:
        await db.close()
        await bot.session.close()
