from __future__ import annotations

import datetime as dt
from html import escape

from bot.config import Config
from bot.i18n import t


def format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(num_bytes: int | float | None, lang: str, *, approx: bool = True) -> str:
    """Человекочитаемый размер файла. approx=True добавляет "≈" — все размеры
    на кнопках разрешений оценочные (см. ytdlp_service._estimate_size_bytes),
    а не точные, так что стоит явно на это намекать."""
    if not num_bytes or num_bytes <= 0:
        return ""
    size = float(num_bytes)
    prefix = "≈" if approx else ""
    units = (
        t(lang, "size_unit_b"),
        t(lang, "size_unit_kb"),
        t(lang, "size_unit_mb"),
        t(lang, "size_unit_gb"),
    )
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == units[0]:
                return f"{prefix}{int(size)} {unit}"
            return f"{prefix}{size:.1f} {unit}"
        size /= 1024
    return f"{prefix}{size:.1f} {units[-1]}"


def format_count(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def build_caption(
    title: str,
    uploader: str | None,
    duration: int | None,
    view_count: int | None,
    lang: str,
) -> str:
    lines = [f"🎬 <b>{escape(title)}</b>"]
    if uploader:
        lines.append(f"👤 {escape(uploader)}")

    meta = []
    if duration:
        meta.append(f"⏱ {format_duration(duration)}")
    if view_count:
        meta.append(f"👁 {format_count(view_count)}")
    if meta:
        lines.append(" · ".join(meta))

    lines.append(t(lang, "choose_resolution"))
    return "\n".join(lines)


def render_progress_bar(fraction: float, width: int = 12) -> str:
    """Текстовый прогресс-бар из блочных символов, например
    '████████░░░░' для fraction=0.66."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled)


def format_audio_download_progress(fraction: float | None, label: str, lang: str) -> str:
    """То же самое, что format_download_progress, но для кнопки "Скачать
    аудио" — там нет разрешения, поэтому текст не привязан к "{height}p".

    label — внутренний, языконезависимый ключ стадии ("video"/"audio"/
    "processing", см. bot/services/ytdlp_service.py::_stream_label и
    _make_postprocessor_hook), НЕ готовый для показа текст — здесь он
    используется только для ветвления "обработка или ещё качаем", сам текст
    для audio-кнопки не зависит от того, video или audio сейчас качается
    (в отличие от format_download_progress ниже, где label ещё и
    показывается в скобках)."""
    if label == "processing":
        return t(lang, "progress_audio_processing")
    if fraction is None:
        return t(lang, "progress_audio_unknown")
    percent = round(fraction * 100)
    bar = render_progress_bar(fraction)
    return t(lang, "progress_audio_percent", bar=bar, percent=percent)


def format_download_progress(height: int, fraction: float | None, label: str, lang: str) -> str:
    """Текст статусного сообщения во время скачивания.

    label — внутренний, языконезависимый ключ того, что сейчас происходит:
    "video"/"audio" (какая дорожка качается) или "processing" (склейка
    видео+аудио через ffmpeg, для неё yt-dlp не сообщает процент) — см.
    bot/services/ytdlp_service.py::_stream_label/_make_postprocessor_hook.
    Переводится в показываемый текст через progress_label_video/
    progress_label_audio (см. bot/i18n.py). fraction=None — доля неизвестна
    (например, yt-dlp не знает общий размер потока или ещё не показывает
    процент).
    """
    if label == "processing":
        return t(lang, "progress_video_processing", height=height)
    label_text = t(lang, f"progress_label_{label}")
    if fraction is None:
        return t(lang, "progress_video_unknown", height=height, label=label_text)
    percent = round(fraction * 100)
    bar = render_progress_bar(fraction)
    return t(
        lang, "progress_video_percent", height=height, label=label_text, bar=bar, percent=percent
    )


def format_history_entry(
    *,
    title: str | None,
    video_id: str | None,
    height: int | None,
    file_size_bytes: int | None,
    created_at: dt.datetime,
    lang: str,
) -> str:
    """Одна строка для команды /history.

    file_size_bytes здесь — РЕАЛЬНЫЙ размер скачанного файла (записан в
    Event после успешной отправки), а не оценка с кнопок разрешений,
    поэтому format_size зовётся с approx=False — без "≈".
    """
    label = escape(title) if title else t(lang, "history_video_fallback_title")
    if video_id:
        label = f'<a href="https://youtu.be/{video_id}">{label}</a>'

    parts = []
    if height:
        parts.append(f"{height}p")
    else:
        parts.append(t(lang, "history_audio_label"))
    size_label = format_size(file_size_bytes, lang, approx=False)
    if size_label:
        parts.append(size_label)
    parts.append(created_at.strftime("%d.%m %H:%M UTC"))

    return f"• {label}\n  {' · '.join(parts)}"


def build_terms_text(support_contact: str | None, lang: str) -> str:
    """Текст команды /terms — условия использования и мини-дисклеймер.

    Без юридической вычитки — это базовый набросок, закрывающий минимум
    "предпосылок" из бизнес-плана (см. docs/business-plan.md): явно
    сказано, что ответственность за соблюдение авторских прав на
    пользователе, и что доступ к конкретному видео может быть закрыт по
    жалобе правообладателя (см. bot/db/models.py::BlockedVideo).
    support_contact — необязательный контакт для таких жалоб (см.
    Config.support_contact); если не задан, используется общая формулировка.
    """
    contact_line = (
        t(lang, "terms_contact_with", contact=support_contact)
        if support_contact
        else t(lang, "terms_contact_without")
    )
    return t(lang, "terms_body", contact_line=contact_line)


def format_file_limit_note(config: Config, lang: str) -> str:
    """Строка для /help про ограничение на размер файла.

    Раньше это был статичный текст с захардкоженными "50 МБ" и "обход в
    разработке" — устарел ещё до фазы 1 этого проекта, когда обход через
    локальный Bot API сервер (docker-compose.yml) был реализован и стал
    опциональным (см. README, "Обход лимита 50 МБ"). Теперь читает
    РЕАЛЬНЫЙ сконфигурированный лимит (Config.max_file_size_mb — 50 по
    умолчанию, до 2000 при поднятом локальном сервере), чтобы текст сам
    не расходился с тем, что бот на самом деле делает.
    """
    if config.telegram_api_base_url:
        return t(lang, "file_limit_note_local_server", mb=config.max_file_size_mb)
    return t(lang, "file_limit_note_default", mb=config.max_file_size_mb)
