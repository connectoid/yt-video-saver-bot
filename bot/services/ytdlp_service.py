from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)

# Разрешения, которые готовы предлагать пользователю, по убыванию популярности.
CURATED_HEIGHTS: list[int] = [1080, 720, 480, 360, 240, 144]
MAX_RESOLUTION_BUTTONS = 4


class VideoUnavailableError(Exception):
    """Видео нельзя получить (приватное, удалено, регион-лок и т.п.)."""


class LiveStreamNotSupportedError(Exception):
    """Ссылка ведёт на текущий прямой эфир."""


class NoFormatsAvailableError(Exception):
    """yt-dlp не вернул ни одного пригодного видеоформата."""


@dataclass
class VideoInfo:
    id: str
    title: str
    uploader: str | None
    duration: int | None
    view_count: int | None
    thumbnail_url: str | None
    available_heights: list[int]
    formats: dict[int, str]  # height -> yt-dlp format selector
    sizes: dict[int, int | None]  # height -> примерный размер файла в байтах (None, если yt-dlp его не знает)


def _base_ydl_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
    }


def _extract_info_sync(url: str) -> dict:
    with YoutubeDL({**_base_ydl_opts(), "skip_download": True}) as ydl:
        return ydl.extract_info(url, download=False)


def _build_format_selector(height: int) -> str:
    # Сначала пробуем честный mp4/m4a (лучше всего проигрывается в Telegram),
    # затем любые видео+аудио дорожки нужной высоты, и как последний
    # резерв — уже смешанный (progressive) поток без необходимости в ffmpeg.
    return (
        f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]"
        f"/bestvideo[height={height}]+bestaudio"
        f"/best[height={height}]"
    )


def _format_size_bytes(fmt: dict) -> int | None:
    """У yt-dlp размер формата бывает либо точным (filesize), либо оценённым
    им самим по битрейту и длительности (filesize_approx) — берём то, что
    есть, само название поля уже говорит вызывающему коду, что это оценка."""
    return fmt.get("filesize") or fmt.get("filesize_approx")


def _best_audio_size_bytes(formats: list[dict]) -> int | None:
    """Размер аудиодорожки, которая будет примешана к видео-потоку — не
    зависит от выбранного разрешения, поэтому считается один раз и
    прибавляется к размеру видео при отдельных (не progressive) форматах.
    Приоритет тот же, что и в _build_format_selector: сначала m4a."""
    audio_formats = [
        f
        for f in formats
        if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")
    ]
    candidates = [f for f in audio_formats if _format_size_bytes(f)]
    if not candidates:
        return None
    best = max(candidates, key=lambda f: (f.get("ext") == "m4a", f.get("abr") or 0))
    return _format_size_bytes(best)


def _estimate_size_bytes(formats: list[dict], height: int) -> int | None:
    """Примерный итоговый размер файла для конкретного разрешения.

    Для большинства видео выше 360p YouTube отдаёt видео и аудио отдельными
    (video-only) потоками, которые склеиваются ffmpeg-ом при скачивании —
    тогда оценка это видео-поток нужной высоты + отдельно взятое лучшее
    аудио. Если видео-only потока такой высоты нет (только progressive,
    уже со звуком) — берём размер progressive-формата как есть, аудио
    добавлять не нужно, оно уже внутри.
    """
    at_height = [
        f
        for f in formats
        if f.get("height") == height and f.get("vcodec") not in (None, "none")
    ]
    video_only = [f for f in at_height if f.get("acodec") in (None, "none")]
    progressive = [f for f in at_height if f.get("acodec") not in (None, "none")]

    video_candidates = [f for f in video_only if _format_size_bytes(f)]
    if video_candidates:
        best_video = max(
            video_candidates, key=lambda f: (f.get("ext") == "mp4", _format_size_bytes(f))
        )
        video_size = _format_size_bytes(best_video)
        audio_size = _best_audio_size_bytes(formats)
        return video_size + audio_size if audio_size else video_size

    progressive_candidates = [f for f in progressive if _format_size_bytes(f)]
    if progressive_candidates:
        best_progressive = max(
            progressive_candidates,
            key=lambda f: (f.get("ext") == "mp4", _format_size_bytes(f)),
        )
        return _format_size_bytes(best_progressive)

    return None


def _select_offered_heights(available_heights: list[int]) -> list[int]:
    """Сгруппировать реально доступные высоты по ближайшему эталонному уровню.

    Раньше высота должна была ТОЧНО совпасть с CURATED_HEIGHTS, из-за чего
    видео с нестандартными значениями высоты (или урезанным набором
    форматов, которые иногда отдаёт YouTube) могло показать всего одну
    кнопку, хотя реальных вариантов было больше. Теперь каждый эталонный
    уровень представлен ближайшей снизу реальной высотой из тех, что
    действительно есть у видео, — кнопки никогда не «теряются» из-за
    несовпадения на пиксель и никогда не дублируют один и тот же файл.
    """
    if not available_heights:
        return []

    top_tier = CURATED_HEIGHTS[0]
    lowest_tier = CURATED_HEIGHTS[-1]
    tier_reps: dict[int, int] = {}
    for h in available_heights:
        # Не предлагаем заметно выше вершины лестницы (1080p) — для Telegram
        # это не даёт пользы, только больший файл, который скорее упрётся
        # в лимит в 50 МБ. Без этой границы 4K/1440p "съедали" бы слот 1080p,
        # т.к. тоже проходили условие h >= 1080.
        if h > top_tier * 1.15:
            continue
        tier = next((c for c in CURATED_HEIGHTS if h >= c), lowest_tier)
        if tier not in tier_reps or h > tier_reps[tier]:
            tier_reps[tier] = h

    if not tier_reps:
        # Видео есть только в качестве заметно выше потолка (например,
        # чистое 4K без более низких дорожек) — предложим лучшее доступное.
        return [max(available_heights)]

    ordered_tiers = [c for c in CURATED_HEIGHTS if c in tier_reps]
    return [tier_reps[t] for t in ordered_tiers][:MAX_RESOLUTION_BUTTONS]


async def fetch_video_info(url: str) -> VideoInfo:
    try:
        info = await asyncio.to_thread(_extract_info_sync, url)
    except DownloadError as exc:
        raise VideoUnavailableError(str(exc)) from exc

    if info.get("is_live"):
        raise LiveStreamNotSupportedError

    formats = info.get("formats") or []
    heights = sorted(
        {
            f.get("height")
            for f in formats
            if f.get("vcodec") not in (None, "none") and f.get("height")
        },
        reverse=True,
    )
    if not heights:
        raise NoFormatsAvailableError

    offered = _select_offered_heights(heights)
    if not offered:
        offered = heights[:1]

    format_map = {h: _build_format_selector(h) for h in offered}
    size_map = {h: _estimate_size_bytes(formats, h) for h in offered}

    return VideoInfo(
        id=info.get("id", ""),
        title=info.get("title") or "Видео",
        uploader=info.get("uploader"),
        duration=info.get("duration"),
        view_count=info.get("view_count"),
        thumbnail_url=info.get("thumbnail"),
        available_heights=offered,
        formats=format_map,
        sizes=size_map,
    )


def _download_sync(url: str, format_selector: str, work_dir: Path) -> Path:
    outtmpl = str(work_dir / "%(title).200B [%(id)s].%(ext)s")
    ydl_opts = {
        **_base_ydl_opts(),
        "format": format_selector,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads") or []
        if downloads and downloads[0].get("filepath"):
            return Path(downloads[0]["filepath"])
        return Path(ydl.prepare_filename(info))


async def download_video(url: str, format_selector: str, work_dir: Path) -> Path:
    try:
        return await asyncio.to_thread(_download_sync, url, format_selector, work_dir)
    except DownloadError as exc:
        raise VideoUnavailableError(str(exc)) from exc
