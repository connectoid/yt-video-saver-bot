from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import Message

from bot.utils.url_utils import extract_video_id


class YouTubeLinkFilter(BaseFilter):
    """Пропускает только сообщения, содержащие ссылку на YouTube-видео/Shorts.

    При совпадении возвращает словарь {"video_url": ..., "video_id": ...},
    который aiogram прокинет в обработчик как именованные аргументы —
    video_id нужен обработчику отдельно от video_url, чтобы можно было
    проверить блок-лист (см. bot/db/crud.py::is_video_blocked) ещё до
    похода в yt-dlp за метаданными.
    """

    async def __call__(self, message: Message) -> bool | dict[str, Any]:
        if not message.text:
            return False
        video_id = extract_video_id(message.text)
        if video_id is None:
            return False
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        return {"video_url": video_url, "video_id": video_id}
