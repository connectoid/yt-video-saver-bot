from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import threading
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.db.models import EventStatus, Stage
from bot.filters.youtube_link import YouTubeLinkFilter
from bot.keyboards.resolution import build_resolution_keyboard
from bot.middlewares.daily_limit import DailyLimitMiddleware
from bot.services import ytdlp_service
from bot.services.download_queue import DownloadQueue, queue_ahead_count
from bot.services.progress_reporter import ProgressReporter
from bot.services.request_cache import PendingDownload, RequestCache
from bot.utils.formatting import build_caption

logger = logging.getLogger(__name__)

router = Router(name="video")
router.callback_query.middleware(DailyLimitMiddleware())

# MVP: одно хранилище на процесс. При масштабировании на несколько
# инстансов бота его нужно будет вынести в Redis/БД (см. README, roadmap).
request_cache = RequestCache()
download_queue = DownloadQueue()

# Активные (в очереди или уже качающиеся) скачивания по user_id — только для
# /cancel. Один пользователь = одно активное скачивание (кнопки разрешений
# после отправки становятся неактуальны для нового запроса, так что этого
# достаточно). task.cancel() прерывает asyncio-часть (ожидание слота в
# семафоре, отправку файла), cancel_event заставляет сам поток yt-dlp
# остановиться пораньше, а не докачивать всё до конца впустую — см.
# ytdlp_service.download_video.
active_downloads: dict[int, tuple[asyncio.Task, threading.Event]] = {}


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

    queue_token = await download_queue.enter()
    position = await download_queue.position(queue_token)
    ahead = queue_ahead_count(position, config.max_concurrent_downloads)
    if ahead > 0:
        status = await message.answer(
            f"🕐 В очереди на скачивание — перед вами: {ahead}. "
            "Начнём, как только освободится слот."
        )
    else:
        status = await message.answer(f"⏳ Скачиваю {height}p...")

    work_dir = Path(tempfile.mkdtemp(prefix="dl_", dir=config.downloads_dir))
    cancel_event = threading.Event()
    active_downloads[user_id] = (asyncio.current_task(), cancel_event)
    try:
        loop = asyncio.get_running_loop()
        progress = ProgressReporter(loop, status, height)
        async with semaphore:
            filepath = await ytdlp_service.download_video(
                pending.url, format_selector, work_dir,
                on_progress=progress, cancel_event=cancel_event,
            )

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

        try:
            # Склейка (ffmpeg -c copy) сама по себе обычно быстрая — долгим
            # чаще оказывается именно аплоад файла в Telegram. Без этого
            # апдейта пользователь всё это время видел бы одну и ту же
            # надпись "Собираю файл" и мог решить, что бот завис.
            await status.edit_text(f"📤 Отправляю {height}p в Telegram...")
        except Exception:
            pass

        await message.answer_video(FSInputFile(filepath), caption=pending.title)
        await status.delete()
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.SUCCESS,
            video_id=pending.video_id,
            title=pending.title,
            height=height,
            file_size_bytes=size_bytes,
        )
    except ytdlp_service.DownloadCancelledError:
        logger.info("Download cancelled by user %s: %s", user_id, pending.url)
        try:
            await status.edit_text("❌ Скачивание отменено.")
        except Exception:
            pass
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.CANCELLED,
            video_id=pending.video_id,
            height=height,
        )
    except asyncio.CancelledError:
        # /cancel вызвал task.cancel() пока мы ещё ждали своей очереди/слота
        # в семафоре (до потока с yt-dlp дело не дошло — иначе поймали бы
        # DownloadCancelledError выше). Отдаём CancelledError обратно после
        # короткой уборки — глотать его молча нельзя, это ломает штатную
        # семантику отмены asyncio-задач.
        logger.info("Download task cancelled for user %s before/while downloading", user_id)
        try:
            await status.edit_text("❌ Скачивание отменено.")
        except Exception:
            pass
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.CANCELLED,
            video_id=pending.video_id,
            height=height,
        )
        raise
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
        # Не затираем чужую запись: если пользователь успел отменить это
        # скачивание и сразу запустить новое, к моменту, когда до этого
        # (уже отменённого) task дойдёт finally, active_downloads[user_id]
        # может уже указывать на СЛЕДУЮЩЕЕ скачивание — трогаем запись,
        # только если она всё ещё про нас.
        current = active_downloads.get(user_id)
        if current is not None and current[0] is asyncio.current_task():
            active_downloads.pop(user_id, None)
        await download_queue.leave(queue_token)
        shutil.rmtree(work_dir, ignore_errors=True)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    entry = active_downloads.get(user_id) if user_id is not None else None
    if entry is None:
        await message.answer("Сейчас у вас нет активных скачиваний.")
        return

    task, cancel_event = entry
    # Оба механизма нужны: cancel_event останавливает сам поток yt-dlp (если
    # скачивание уже реально идёт — иначе поток докачает всё впустую и
    # впустую займёт канал/CPU уже после того, как мы всё равно всё бросили),
    # task.cancel() — прерывает ожидание своей очереди/слота в семафоре или
    # отправку файла в Telegram, если до потока ещё не дошло или уже после
    # него. Само подтверждение пользователю уходит из handle_resolution_choice
    # (там обновляется то же статусное сообщение, что показывало прогресс).
    cancel_event.set()
    task.cancel()
    await message.answer("Отменяю скачивание...")


@router.message(F.text)
async def handle_other_text(message: Message) -> None:
    await message.answer("Пришлите, пожалуйста, ссылку на видео или Shorts с YouTube.")
