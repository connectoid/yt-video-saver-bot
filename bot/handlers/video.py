from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import threading
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.config import Config
from bot.db import crud
from bot.db.engine import Database
from bot.db.models import EventStatus, Stage
from bot.filters.youtube_link import YouTubeLinkFilter
from bot.handlers.feedback import FeedbackStates
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


async def _is_blocked_safe(db: Database | None, video_id: str) -> bool:
    """Обёртка над crud.is_video_blocked. Если БД недоступна — считаем
    видео НЕ заблокированным (fail-open), тем же способом, каким
    DailyLimitMiddleware обрабатывает недоступность БД для дневного
    лимита: блок-лист — это защита от юридических рисков, а не от
    злоупотреблений, отказ ради него в обслуживании при сбое БД того не
    стоит."""
    if db is None:
        return False
    try:
        return await crud.is_video_blocked(db, video_id)
    except Exception:
        logger.exception("Failed to check blocklist for video_id=%s", video_id)
        return False


@router.message(YouTubeLinkFilter())
async def handle_link(
    message: Message,
    video_url: str,
    video_id: str,
    db: Database | None = None,
    config: Config | None = None,
) -> None:
    user_id = message.from_user.id if message.from_user else None

    if await _is_blocked_safe(db, video_id):
        await message.answer(
            "🚫 Это видео недоступно для скачивания — доступ закрыт по "
            "запросу правообладателя."
        )
        if user_id is not None:
            await _log_event_safe(
                db,
                user_id=user_id,
                stage=Stage.INFO_FETCH,
                status=EventStatus.BLOCKED_VIDEO,
                video_id=video_id,
            )
        return

    status = await message.answer("🔎 Получаю информацию о видео...")

    cookies_file = config.cookies_file if config else None
    try:
        info = await ytdlp_service.fetch_video_info(video_url, cookies_file=cookies_file)
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
        PendingDownload(
            url=video_url,
            video_id=info.id,
            title=info.title,
            uploader=info.uploader,
            formats=info.formats,
            audio_format=info.audio_format,
        )
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


async def _perform_download(
    *,
    callback: CallbackQuery,
    semaphore: asyncio.Semaphore,
    config: Config,
    db: Database | None,
    pending: PendingDownload,
    format_selector: str,
    height: int | None,
    merge_output_format: str | None,
) -> None:
    """Общий код скачивания + отправки файла — используется и видео-кнопками
    (handle_resolution_choice), и кнопкой "Скачать аудио" (handle_audio_choice).

    height=None означает аудио: меняются тексты статусных сообщений, каким
    методом отправляется файл в Telegram (answer_audio вместо answer_video)
    и что попадает в Event.height — NULL для DOWNLOAD-события используется
    в аналитике как признак "это была audio-кнопка, а не разрешение" (см.
    bot/db/crud.py::get_stats — audio_downloads_success_today; для видео
    height всегда задан явно из callback_data, так что двусмысленности
    с существующими данными не возникает).
    """
    user_id = callback.from_user.id
    target_label = f"{height}p" if height is not None else "аудио"

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
        status = await message.answer(f"⏳ Скачиваю {target_label}...")

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
                merge_output_format=merge_output_format,
                cookies_file=config.cookies_file,
            )

        size_bytes = filepath.stat().st_size
        if size_bytes > config.max_file_size_bytes:
            note = (
                "Обход лимита в разработке — попробуйте разрешение поменьше."
                if height is not None
                else "Обход лимита в разработке — для этого видео аудио без "
                "сжатия в лимит пока не помещается."
            )
            await status.edit_text(
                f"⚠️ Файл получился {size_bytes / (1024 * 1024):.1f} МБ — это больше "
                f"лимита Telegram для ботов ({config.max_file_size_mb} МБ). {note}"
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
            await status.edit_text(f"📤 Отправляю {target_label} в Telegram...")
        except Exception:
            pass

        if height is not None:
            await message.answer_video(FSInputFile(filepath), caption=pending.title)
        else:
            # title/performer — то, что Telegram покажет прямо в плеере, не
            # зависит от ID3-тегов внутри файла (у m4a/webm от YouTube их
            # обычно и нет) — берём из уже извлечённых метаданных видео.
            await message.answer_audio(
                FSInputFile(filepath), title=pending.title, performer=pending.uploader
            )
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
        logger.exception("Failed to download %s (%s)", pending.url, target_label)
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

    if pending.video_id and await _is_blocked_safe(db, pending.video_id):
        # Редкий, но реальный случай: кнопки разрешений уже были показаны,
        # когда админ заблокировал видео (см. /block в bot/handlers/admin.py)
        # — проверяем ещё раз здесь, чтобы блокировка применялась сразу же,
        # а не только к новым запросам /handle_link.
        await callback.answer(
            "Это видео недоступно для скачивания — доступ закрыт по запросу "
            "правообладателя.",
            show_alert=True,
        )
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.BLOCKED_VIDEO,
            video_id=pending.video_id,
            height=height,
        )
        return

    format_selector = pending.formats.get(height)
    if format_selector is None:
        await callback.answer("Это разрешение больше недоступно.", show_alert=True)
        return

    await _perform_download(
        callback=callback,
        semaphore=semaphore,
        config=config,
        db=db,
        pending=pending,
        format_selector=format_selector,
        height=height,
        merge_output_format="mp4",
    )


@router.callback_query(F.data.startswith("dla:"))
async def handle_audio_choice(
    callback: CallbackQuery,
    semaphore: asyncio.Semaphore,
    config: Config,
    db: Database | None = None,
) -> None:
    """Кнопка "🎵 Скачать аудио" — та же механика, что и у видео
    (handle_resolution_choice), но без разрешения: одна дорожка лучшего
    доступного качества, без ffmpeg-склейки/перекодирования (см.
    ytdlp_service.AUDIO_FORMAT_SELECTOR)."""
    assert callback.data is not None
    _, request_id = callback.data.split(":")
    user_id = callback.from_user.id

    pending = request_cache.get(request_id)
    if pending is None:
        await callback.answer("Ссылка устарела, отправьте видео ещё раз.", show_alert=True)
        return

    if pending.video_id and await _is_blocked_safe(db, pending.video_id):
        await callback.answer(
            "Это видео недоступно для скачивания — доступ закрыт по запросу "
            "правообладателя.",
            show_alert=True,
        )
        await _log_event_safe(
            db,
            user_id=user_id,
            stage=Stage.DOWNLOAD,
            status=EventStatus.BLOCKED_VIDEO,
            video_id=pending.video_id,
        )
        return

    await _perform_download(
        callback=callback,
        semaphore=semaphore,
        config=config,
        db=db,
        pending=pending,
        format_selector=pending.audio_format,
        height=None,
        merge_output_format=None,
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """/cancel — универсальная отмена "того, что сейчас происходит" для
    пользователя: активного скачивания и/или ожидания сообщения для
    /feedback (bot/handlers/feedback.py). Оба независимы и проверяются по
    отдельности — можно, например, попасть в /feedback, находясь при этом
    без активных загрузок, и наоборот."""
    user_id = message.from_user.id if message.from_user else None
    entry = active_downloads.get(user_id) if user_id is not None else None

    cancelled_something = False

    if entry is not None:
        task, cancel_event = entry
        # Оба механизма нужны: cancel_event останавливает сам поток yt-dlp
        # (если скачивание уже реально идёт — иначе поток докачает всё
        # впустую и займёт канал/CPU уже после того, как мы всё равно всё
        # бросили), task.cancel() — прерывает ожидание своей очереди/слота
        # в семафоре или отправку файла в Telegram, если до потока ещё не
        # дошло или уже после него. Финальное сообщение про отмену самого
        # скачивания уходит из handle_resolution_choice (там обновляется
        # то же статусное сообщение, что показывало прогресс).
        cancel_event.set()
        task.cancel()
        await message.answer("Отменяю скачивание...")
        cancelled_something = True

    if await state.get_state() == FeedbackStates.waiting_for_message.state:
        await state.clear()
        await message.answer("Хорошо, ничего не отправляю администратору.")
        cancelled_something = True

    if not cancelled_something:
        await message.answer("Сейчас нечего отменять.")


@router.message(F.text)
async def handle_other_text(message: Message) -> None:
    await message.answer("Пришлите, пожалуйста, ссылку на видео или Shorts с YouTube.")
