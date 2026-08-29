from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.db.models import EventStatus, Stage
from bot.filters.youtube_link import YouTubeLinkFilter
from bot.keyboards.resolution import build_resolution_keyboard
from bot.middlewares.daily_limit import DailyLimitMiddleware
from bot.services import ytdlp_service
from bot.services.request_cache import PendingDownload, RequestCache
from bot.utils.formatting import build_caption

logger = logging.getLogger(__name__)

router = Router(name="video")
router.callback_query.middleware(DailyLimitMiddleware())

# MVP: одно хранилище на процесс. При масштабировании на несколько
# инстансов бота его нужно будет вынести в Redis/БД (см. README, roadmap).
request_cache = RequestCache()


async def _log_event_safe(db: Database | None, **kwargs) -> None:
    """Обёртка над crud.log_event: аналитика не должна ронять обработчик,
    если БД временно недоступна."""
    if db is None:
        return
    try:
        await crud.log_event(db, **kwargs)
    except Exception:
        logger.exception("Failed to log event: %s", kwargs)


@router.message(YouTubeLinkFilter())
async def handle_link(message: Message, video_url: str, db: Database | None = None) -> None:
    user_id = message.from_user.id if message.from_user else None
    status = await message.answer("🔎 Получаю информацию о видео...")

    try:
        info = await ytdlp_service.fetch_video_info(video_url)
    except ytdlp_service.LiveStreamNotSupportedError:
        await status.edit_text("⚠️ Прямые эфиры пока не поддерживаются.")
        if user_id is not None:
            await _log_event_safe(
                db, user_id=user_id, stage=Stage.INFO_FETCH, status=EventStatus.FAILED_LIVE
            )
        return
    except ytdlp_service.NoFormatsAvailableError:
        await status.edit_text("⚠️ Не удалось найти доступные форматы для этого видео.")
        if user_id is not None:
            await _log_event_safe(
                db, user_id=user_id, stage=Stage.INFO_FETCH, status=EventStatus.FAILED_NO_FORMATS
            )
        return
    except ytdlp_service.VideoUnavailableError as exc:
        logger.info("Video unavailable for %s: %s", video_url, exc)
        await status.edit_text(
            "⚠️ Не получилось получить это видео. Возможно, оно приватное, "
            "удалено или недоступно в регионе, где работает бот."
        )
        if user_id is not None:
            await _log_event_safe(
                db,
                user_id=user_id,
                stage=Stage.INFO_FETCH,
                status=EventStatus.FAILED_UNAVAILABLE,
            )
        return
    except Exception:
        logger.exception("Failed to fetch video info for %s", video_url)
        await status.edit_text("⚠️ Что-то пошло не так при получении видео. Попробуйте позже.")
        if user_id is not None:
            await _log_event_safe(
                db, user_id=user_id, stage=Stage.INFO_FETCH, status=EventStatus.FAILED_ERROR
            )
        return

    if user_id is not None:
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.INFO_FETCH,
            status=EventStatus.SUCCESS,
            video_id=info.id,
        )

    request_id = request_cache.put(
        PendingDownload(url=video_url, video_id=info.id, title=info.title, formats=info.formats)
    )
    keyboard = build_resolution_keyboard(request_id, info.available_heights, info.sizes)
    caption = build_caption(info.title, info.uploader, info.duration, info.view_count)

    await status.delete()
    if info.thumbnail_url:
        try:
            await message.answer_photo(info.thumbnail_url, caption=caption, reply_markup=keyboard)
            return
        except Exception:
            logger.warning("Failed to send thumbnail for %s, falling back to text", video_url)
    await message.answer(caption, reply_markup=keyboard)


@router.callback_query(F.data.startswith("dl:"))
async def handle_resolution_choice(
    callback: CallbackQuery,
    semaphore: asyncio.Semaphore,
    config: Config,
    db: Database | None = None,
) -> None:
    assert callback.data is not None
    _, request_id, height_str = callback.data.split(":")
    height = int(height_str)
    user_id = callback.from_user.id

    pending = request_cache.get(request_id)
    if pending is None:
        await callback.answer("Ссылка устарела, отправьте видео ещё раз.", show_alert=True)
        return

    format_selector = pending.formats.get(height)
    if format_selector is None:
        await callback.answer("Это разрешение больше недоступно.", show_alert=True)
        return

    await callback.answer()
    message = callback.message
    if message is None:
        return

    status = await message.answer(f"⏳ Скачиваю {height}p...")

    work_dir = Path(tempfile.mkdtemp(prefix="dl_", dir=config.downloads_dir))
    try:
        async with semaphore:
            filepath = await ytdlp_service.download_video(pending.url, format_selector, work_dir)

        size_bytes = filepath.stat().st_size
        if size_bytes > config.max_file_size_bytes:
            await status.edit_text(
                f"⚠️ Файл получился {size_bytes / (1024 * 1024):.1f} МБ — это больше "
                f"лимита Telegram для ботов ({config.max_file_size_mb} МБ). "
                "Обход лимита в разработке — попробуйте разрешение поменьше."
            )
            await _log_event_safe(
                db,
                user_id=user_id,
                stage=Stage.DOWNLOAD,
                status=EventStatus.FAILED_SIZE_LIMIT,
                video_id=pending.video_id,
                height=height,
                file_size_bytes=size_bytes,
            )
            return

        await message.answer_video(FSInputFile(filepath), caption=pending.title)
        await status.delete()
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.SUCCESS,
            video_id=pending.video_id,
            height=height,
            file_size_bytes=size_bytes,
        )
    except ytdlp_service.VideoUnavailableError:
        logger.info("Video became unavailable during download: %s", pending.url)
        await status.edit_text("⚠️ Видео стало недоступно во время скачивания.")
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.FAILED_UNAVAILABLE,
            video_id=pending.video_id,
            height=height,
        )
    except Exception:
        logger.exception("Failed to download %s at %sp", pending.url, height)
        await status.edit_text("⚠️ Не удалось скачать видео. Попробуйте ещё раз позже.")
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.FAILED_ERROR,
            video_id=pending.video_id,
            height=height,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@router.message(F.text)
async def handle_other_text(message: Message) -> None:
    await message.answer("Пришлите, пожалуйста, ссылку на видео или Shorts с YouTube.")
