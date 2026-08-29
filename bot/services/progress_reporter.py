from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from bot.utils.formatting import format_download_progress
from bot.utils.throttle import should_emit_progress

logger = logging.getLogger(__name__)


class ProgressReporter:
    """Мост между синхронным progress_hook yt-dlp и Telegram.

    yt-dlp качает видео в отдельном потоке (см. asyncio.to_thread в
    ytdlp_service.download_video) и зовёт progress_hook/postprocessor_hook
    оттуда же, синхронно — из этого потока нельзя напрямую await-нуть
    aiogram. Экземпляр этого класса передаётся в yt-dlp как обычный
    callable; при вызове он троттлит апдейты (should_emit_progress) и
    планирует редактирование статусного сообщения в event loop бота через
    asyncio.run_coroutine_threadsafe.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, status_message: Any, height: int) -> None:
        self._loop = loop
        self._status = status_message
        self._height = height
        self._lock = threading.Lock()
        self._last_sent_at: float | None = None
        self._last_fraction: float | None = None
        self._last_label: str | None = None

    def __call__(self, fraction: float | None, label: str) -> None:
        """Вызывается синхронно из потока скачивания yt-dlp."""
        now = time.monotonic()
        with self._lock:
            emit = should_emit_progress(
                last_sent_at=self._last_sent_at,
                last_fraction=self._last_fraction,
                last_label=self._last_label,
                now=now,
                fraction=fraction,
                label=label,
            )
            if not emit:
                return
            self._last_sent_at = now
            self._last_fraction = fraction
            self._last_label = label

        text = format_download_progress(self._height, fraction, label)
        try:
            asyncio.run_coroutine_threadsafe(self._edit(text), self._loop)
        except RuntimeError:
            # Event loop уже закрыт (бот завершается) — прогресс всё равно
            # никому не покажется, просто игнорируем.
            logger.debug("Event loop unavailable for progress update", exc_info=True)

    async def _edit(self, text: str) -> None:
        try:
            await self._status.edit_text(text)
        except Exception:
            # Например, "message is not modified" (текст совпал с прошлым)
            # или сообщение уже удалено — не критично, это просто индикатор
            # прогресса, а не что-то, от чего зависит скачивание.
            logger.debug("Failed to edit progress message", exc_info=True)
