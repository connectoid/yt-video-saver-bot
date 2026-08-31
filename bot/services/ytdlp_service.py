from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

try:
    # Официальный способ прервать скачивание yt-dlp изнутри — поднять это
    # исключение из progress_hooks/postprocessor_hooks (см. README yt-dlp,
    # раздел про хуки). Есть в yt-dlp давно, но на случай очень старой
    # версии в окружении — мягкий fallback ниже, чтобы бот не падал на
    # импорте: cancel_event всё равно остановит поток, просто без
    # "красивого" отличия от прочих ошибок yt-dlp внутри самого yt-dlp.
    from yt_dlp.utils import DownloadCancelled
except ImportError:  # pragma: no cover - зависит от версии yt-dlp
    class DownloadCancelled(DownloadError):  # type: ignore[no-redef]
        pass

logger = logging.getLogger(__name__)

# Разрешения, которые готовы предлагать пользователю, по убыванию популярности.
CURATED_HEIGHTS: list[int] = [1080, 720, 480, 360, 240, 144]
MAX_RESOLUTION_BUTTONS = 4

# Аудио-кнопка ("Скачать аудио") — качаем лучшую доступную аудиодорожку как
# есть, без перекодирования в mp3 (это был бы отдельный ffmpeg-проход с
# реальным CPU-кодированием, а не просто извлечение/ремукс, как сейчас у
# видео-склейки — см. project_roadmap про экономию CPU на VPS). Из-за этого
# итоговый файл может быть не только m4a, но и webm/opus — Telegram всё
# равно принимает и проигрывает такие файлы через send_audio, официальная
# рекомендация "только mp3/m4a" касается красивого отображения в
# музыкальном плеере, а не того, отправится ли файл вообще.
AUDIO_FORMAT_SELECTOR = "bestaudio/best"


class VideoUnavailableError(Exception):
    """Видео нельзя получить (приватное, удалено, регион-лок и т.п.)."""


class LiveStreamNotSupportedError(Exception):
    """Ссылка ведёт на текущий прямой эфир."""


class NoFormatsAvailableError(Exception):
    """yt-dlp не вернул ни одного пригодного видеоформата."""


class DownloadCancelledError(Exception):
    """Скачивание прервано пользователем через /cancel."""


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
    audio_format: str  # yt-dlp format selector для кнопки "Скачать аудио"


def _base_ydl_opts(cookies_file: Path | None = None) -> dict:
    # 2026-08-31: раньше здесь стоял жёсткий extractor_args["player_client"]
    # (сначала tv/web_safari, потом web_safari/web под куки) — это было
    # попыткой обойти "Sign in to confirm you're not a bot" на датацентровом
    # VPS. На практике оверрайд оказался ХУЖЕ дефолта: он вручную сужал
    # набор клиентов, которые yt-dlp опрашивает, и как раз выкидывал те,
    # что не попадают под форсированный SABR-стриминг у YouTube. Когда
    # добавили куки поверх узкого списка [web_safari, web] — сломалось
    # полностью (только storyboard-форматы).
    #
    # Проверено на реальном видео (yt-dlp 2026.08.19): без player_client
    # вообще, только с cookiefile — yt-dlp получает нормальные video-only
    # (avc1/vp9/av01, все разрешения вплоть до 4K60) и audio-only
    # (m4a/opus, обе дорожки en-US и ru) форматы с настоящими https-URL.
    # PO Token Providers при этом "none" — специальный provider не нужен.
    # Предупреждение "YouTube is forcing SABR streaming for this client"
    # относится только к части форматов у web-клиента конкретно — другие
    # клиенты в дефолтном наборе это компенсируют, so downloadable formats
    # остаются. НЕ добавляй сюда обратно ручной player_client без свежей
    # проверки через -F -v на реальном видео — история этого файла
    # показывает, что "интуитивно правильный" список клиентов регулярно
    # оказывается хуже, чем дефолт yt-dlp.
    #
    # Если проблема "Sign in to confirm you're not a bot" вернётся на
    # видео БЕЗ куки — см. README, решение через PO-token-provider, это
    # единственный по-настоящему надёжный фикс для форсированного SABR,
    # а не подмена списка клиентов.
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
    }
    if cookies_file:
        opts["cookiefile"] = str(cookies_file)
    return opts


def _extract_info_sync(url: str, cookies_file: Path | None = None) -> dict:
    with YoutubeDL({**_base_ydl_opts(cookies_file), "skip_download": True}) as ydl:
        return ydl.extract_info(url, download=False)


def _build_format_selector(height: int) -> str:
    # Сначала пробуем честный mp4/m4a (лучше всего проигрывается в Telegram),
    # затем любые видео+аудио дорожки нужной высоты, и как последний
    # резерв — уже смешанный (progressive) поток без необходимости в ffmpeg.
    #
    # Последние два варианта (height<=/без ограничения вовсе) — фолбэк на
    # случай, если формат, который был доступен при показе кнопок
    # (fetch_video_info), к моменту фактического скачивания пропал из
    # ответа YouTube (найдено на проде 2026-08-31: ERROR: Requested format
    # is not available — конкретная высота, показанная на кнопке, не
    # нашлась при повторном extract_info на скачивании). Раньше это было
    # жёстким отказом без вариантов: без catch-all весь селектор мог не
    # совпасть НИ С ЧЕМ, если YouTube между двумя запросами отдал другой
    # набор форматов (client-специфичное поведение — тем более вероятно
    # после перехода на web_safari/web для кук, см. README про ошибку
    # входа). Раньше пропустить целевую высоту и получить более низкое
    # качество без предупреждения было немыслимо (жёсткий отказ был
    # единственным исходом) — теперь это осознанный компромисс: лучше
    # скачать похожее качество, чем ничего.
    return (
        f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]"
        f"/bestvideo[height={height}]+bestaudio"
        f"/best[height={height}]"
        f"/best[height<={height}]"
        f"/best"
    )


def _format_size_bytes(fmt: dict) -> int | None:
    """У yt-dlp размер формата бывает либо точным (filesize), либо оценённым
    им самим по битрейту и длительности (filesize_approx) — берём то, что
    есть, само название поля уже говорит вызывающему коду, что это оценка."""
    return fmt.get("filesize") or fmt.get("filesize_approx")


def _pick_preferred(candidates: list[dict], *, preferred_ext: str) -> dict:
    """Выбрать из кандидатов тот, который реальнее всего совпадает с тем,
    что заберёт yt-dlp при скачивании.

    ВАЖНО: раньше здесь был max(..., key=filesize) — брался самый ТЯЖЁЛЫЙ
    файл среди кандидатов. Это систематически завышало оценку: если для
    высоты есть несколько потоков (например VP9 и AV1 — AV1 обычно заметно
    легче при сопоставимом качестве), yt-dlp мог выбрать лёгкий, а мы
    оценивали по тяжёлому. yt-dlp возвращает info["formats"] уже
    отсортированным по своему внутреннему приоритету качества — от худшего
    к лучшему (так же на этом полагается его собственный селектор "best"),
    поэтому предпочтительный кандидат — последний в списке подходящих, а
    не самый большой по размеру.
    """
    preferred = [f for f in candidates if f.get("ext") == preferred_ext]
    pool = preferred or candidates
    return pool[-1]


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
    best = _pick_preferred(candidates, preferred_ext="m4a")
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
        best_video = _pick_preferred(video_candidates, preferred_ext="mp4")
        video_size = _format_size_bytes(best_video)
        audio_size = _best_audio_size_bytes(formats)
        return video_size + audio_size if audio_size else video_size

    progressive_candidates = [f for f in progressive if _format_size_bytes(f)]
    if progressive_candidates:
        best_progressive = _pick_preferred(progressive_candidates, preferred_ext="mp4")
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


async def fetch_video_info(url: str, cookies_file: Path | None = None) -> VideoInfo:
    try:
        info = await asyncio.to_thread(_extract_info_sync, url, cookies_file)
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
        audio_format=AUDIO_FORMAT_SELECTOR,
    )


def _stream_label(info: dict) -> str:
    vcodec = info.get("vcodec")
    acodec = info.get("acodec")
    has_video = vcodec not in (None, "none")
    has_audio = acodec not in (None, "none")
    if has_video and not has_audio:
        return "видео"
    if has_audio and not has_video:
        return "аудио"
    return "видео"


def _make_progress_hook(
    on_progress: Callable[[float | None, str], None],
    cancel_event: threading.Event | None,
):
    def hook(d: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            # Пользователь нажал /cancel — прерываем скачивание изнутри
            # потока прямо здесь, не дожидаясь следующего шага. progress_hook
            # зовётся часто (по мере получения чанков), поэтому реакция
            # почти мгновенная.
            raise DownloadCancelled("Cancelled by user")
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            fraction = downloaded / total if total else None
            label = _stream_label(d.get("info_dict") or {})
            on_progress(fraction, label)
        elif status == "finished":
            label = _stream_label(d.get("info_dict") or {})
            on_progress(1.0, label)

    return hook


def _make_postprocessor_hook(
    on_progress: Callable[[float | None, str], None],
    cancel_event: threading.Event | None,
):
    def hook(d: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            # Пойманное здесь отменяет только до старта ffmpeg-слияния — сам
            # ffmpeg-процесс (если уже запущен) достучаться и прервать так
            # нельзя, но эта стадия обычно быстрая (секунды).
            raise DownloadCancelled("Cancelled by user")
        if d.get("status") == "started":
            on_progress(None, "обработка")

    return hook


def _download_sync(
    url: str,
    format_selector: str,
    work_dir: Path,
    on_progress: Callable[[float | None, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    merge_output_format: str | None = "mp4",
    cookies_file: Path | None = None,
) -> Path:
    outtmpl = str(work_dir / "%(title).200B [%(id)s].%(ext)s")
    ydl_opts = {
        **_base_ydl_opts(cookies_file),
        "format": format_selector,
        "outtmpl": outtmpl,
    }
    if merge_output_format:
        # Для аудио (см. download_video) merge_output_format=None — качаем
        # одну дорожку как есть, форсировать контейнер тут не нужно.
        ydl_opts["merge_output_format"] = merge_output_format
    if on_progress is not None:
        ydl_opts["progress_hooks"] = [_make_progress_hook(on_progress, cancel_event)]
        ydl_opts["postprocessor_hooks"] = [_make_postprocessor_hook(on_progress, cancel_event)]
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads") or []
        if downloads and downloads[0].get("filepath"):
            return Path(downloads[0]["filepath"])
        return Path(ydl.prepare_filename(info))


async def download_video(
    url: str,
    format_selector: str,
    work_dir: Path,
    on_progress: Callable[[float | None, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    merge_output_format: str | None = "mp4",
    cookies_file: Path | None = None,
) -> Path:
    """on_progress(fraction, label) вызывается синхронно из потока скачивания
    (см. asyncio.to_thread ниже) — не aiogram/asyncio-safe напрямую, вызывающий
    код (см. ProgressReporter) сам отвечает за безопасный мост в event loop.

    cancel_event — если он выставлен (threading.Event.set()) из другого
    потока/корутины, скачивание прерывается изнутри при следующем вызове
    прогресс-хука (см. _make_progress_hook). Отдельно от этого, отмена самой
    asyncio.Task (например через Task.cancel(), пока мы ещё ждём своей
    очереди/слота в семафоре — до вызова этой функции дело не дошло) —
    обычный asyncio.CancelledError, cancel_event для неё не нужен.

    merge_output_format — контейнер, в который yt-dlp сведёт video+audio
    (по умолчанию mp4, как раньше). Для аудио-кнопки (см.
    handlers/video.py::handle_audio_choice) передаётся None — качается одна
    дорожка как есть, без ffmpeg-склейки/перекодирования.
    """
    try:
        return await asyncio.to_thread(
            _download_sync,
            url,
            format_selector,
            work_dir,
            on_progress,
            cancel_event,
            merge_output_format,
            cookies_file,
        )
    except DownloadCancelled as exc:
        raise DownloadCancelledError(str(exc)) from exc
    except DownloadError as exc:
        raise VideoUnavailableError(str(exc)) from exc
