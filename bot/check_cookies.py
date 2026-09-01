from __future__ import annotations

import asyncio
import logging
import sys

from yt_dlp.utils import DownloadError

from bot.config import Config, load_config
from bot.logging_config import setup_logging
from bot.main import _build_bot
from bot.services.ytdlp_service import _extract_info_sync

logger = logging.getLogger(__name__)

# Стабильное, всегда доступное видео для проверки: не приватное, не
# возрастное, не регион-лок — иначе ложные срабатывания было бы не
# отличить от реально протухших кук. "Never Gonna Give You Up" по
# историческим причинам один из самых живучих роликов на YouTube вообще.
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# YouTube иногда отдаёт временный сбой не связанный с куками (сетевой
# blip, rate-limit) — один повтор с паузой отсекает большинство ложных
# тревог, не давая при этом протухшим кукам "самовылечиться" за счёт
# ретраев (протухшая кука не станет рабочей от повторного запроса).
RETRY_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 15


def _has_downloadable_audio(info: dict) -> bool:
    """Тот же критерий, которым 2026-08-31 руками проверяли протухшие куки
    на проде (см. bot/services/ytdlp_service.py::_base_ydl_opts про
    историю SABR-проблемы — этот скрипт её же мониторит): реальный
    audio-only формат с прямой https-ссылкой, а не только m3u8-плейлист
    без URL. Когда YouTube форсирует SABR из-за плохих кук, yt-dlp
    возвращает только storyboard/m3u8-заглушки — скачать по ним нечего.
    """
    for fmt in info.get("formats") or []:
        if fmt.get("vcodec") not in (None, "none"):
            continue  # это видео-дорожка, а не аудио — не то, что ищем
        if fmt.get("acodec") in (None, "none"):
            continue
        if not fmt.get("url"):
            continue
        if fmt.get("protocol") in ("m3u8", "m3u8_native"):
            continue
        return True
    return False


async def _check_once(config: Config) -> tuple[bool, str]:
    """(healthy, reason) — reason заполнен только когда healthy=False."""
    if config.cookies_file is None:
        # Бот сконфигурирован работать без кук вовсе — проверять нечего.
        return True, ""

    if not config.cookies_file.exists():
        return False, f"файл кук не найден на диске: {config.cookies_file}"

    try:
        info = await asyncio.to_thread(
            _extract_info_sync, TEST_VIDEO_URL, config.cookies_file
        )
    except DownloadError as exc:
        return False, f"yt-dlp упал с ошибкой: {exc}"

    if not _has_downloadable_audio(info):
        return False, (
            "yt-dlp вернул только storyboard/m3u8-форматы без прямых "
            "ссылок — похоже на форсированный SABR из-за протухших/"
            "невалидных кук"
        )

    return True, ""


async def _check_with_retries(config: Config) -> tuple[bool, str]:
    reason = ""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        healthy, reason = await _check_once(config)
        if healthy:
            return True, ""
        if attempt < RETRY_ATTEMPTS:
            logger.warning(
                "Проверка кук не прошла (попытка %s/%s): %s — повтор через %sс",
                attempt, RETRY_ATTEMPTS, reason, RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)
    return False, reason


async def _notify_admins(config: Config, reason: str) -> None:
    if not config.admin_user_ids:
        logger.error(
            "Куки протухли (%s), но ADMIN_USER_IDS пуст — оповещать некого.",
            reason,
        )
        return

    bot = _build_bot(config.bot_token, config.telegram_api_base_url)
    text = (
        "⚠️ <b>yt-video-saver-bot: проблема с cookies.txt</b>\n\n"
        f"Проверка на тестовом видео провалилась:\n{reason}\n\n"
        f"Файл: <code>{config.cookies_file}</code>\n\n"
        "Нужно обновить куки (см. README, раздел про \"Sign in to confirm "
        "you're not a bot\") — экспортировать свежие с запасного аккаунта "
        "и заменить файл на сервере."
    )
    try:
        for admin_id in config.admin_user_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                logger.exception(
                    "Не удалось отправить оповещение админу %s", admin_id
                )
    finally:
        await bot.session.close()


async def main() -> None:
    config = load_config()
    setup_logging(config.log_level)

    healthy, reason = await _check_with_retries(config)

    if healthy:
        logger.info("Куки в порядке (проверено на %s).", TEST_VIDEO_URL)
        return

    logger.error("Куки протухли или невалидны: %s", reason)
    await _notify_admins(config, reason)
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
