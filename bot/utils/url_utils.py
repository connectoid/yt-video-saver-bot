from __future__ import annotations

import re

_YOUTUBE_HOST = r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)"

YOUTUBE_URL_RE = re.compile(
    rf"""
    {_YOUTUBE_HOST}
    (?:
        /watch\?(?:[\w=&%-]*&)?v=(?P<id1>[\w-]{{11}})
      | /shorts/(?P<id2>[\w-]{{11}})
      | /live/(?P<id3>[\w-]{{11}})
      | /(?P<id4>[\w-]{{11}})            # youtu.be/<id> и youtube.com/<id>
    )
    (?:[?&][\w=&%.-]*)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Форма самого video_id (без ссылки вокруг) — используется при ручном вводе
# id в админ-командах /block и /unblock (см. bot/handlers/admin.py), чтобы
# отсечь опечатки до похода в БД.
VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")


def extract_video_id(text: str) -> str | None:
    """Найти id первой ссылки на YouTube-видео/Shorts в произвольном тексте.

    Вынесено отдельно от extract_video_url, потому что id нужен и до
    похода в yt-dlp — например, чтобы проверить видео по блок-листу
    (см. bot/db/crud.py::is_video_blocked), не тратя время на сетевой
    запрос ради видео, которое всё равно будет отклонено.
    """
    match = YOUTUBE_URL_RE.search(text)
    if not match:
        return None
    return next(g for g in match.groups() if g)


def extract_video_url(text: str) -> str | None:
    """Найти первую ссылку на YouTube-видео/Shorts в произвольном тексте.

    Возвращает канонический watch-URL или None, если ссылка не найдена.
    """
    video_id = extract_video_id(text)
    if video_id is None:
        return None
    return f"https://www.youtube.com/watch?v={video_id}"
