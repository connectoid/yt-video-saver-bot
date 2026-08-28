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


def extract_video_url(text: str) -> str | None:
    """Найти первую ссылку на YouTube-видео/Shorts в произвольном тексте.

    Возвращает канонический watch-URL или None, если ссылка не найдена.
    """
    match = YOUTUBE_URL_RE.search(text)
    if not match:
        return None
    video_id = next(g for g in match.groups() if g)
    return f"https://www.youtube.com/watch?v={video_id}"
