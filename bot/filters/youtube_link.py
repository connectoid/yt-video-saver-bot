from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import Message

from bot.utils.url_utils import extract_video_url


class YouTubeLinkFilter(BaseFilter):
    """Пропускает только сообщения, содержащие ссылку на YouTube-видео/Shorts.

    При совпадении возвращает словарь {"video_url": ...}, который aiogram
    прокинет в обработчик как именованный аргумент.
    """

    async def __call__(self, message: Message) -> bool | dict[str, Any]:
        if not message.text:
            return False
        video_url = extract_video_url(message.text)
        if video_url is None:
            return False
        return {"video_url": video_url}
