from __future__ import annotations

import datetime as dt
from html import escape


def format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(num_bytes: int | float | None, *, approx: bool = True) -> str:
    """Человекочитаемый размер файла. approx=True добавляет "≈" — все размеры
    на кнопках разрешений оценочные (см. ytdlp_service._estimate_size_bytes),
    а не точные, так что стоит явно на это намекать."""
    if not num_bytes or num_bytes <= 0:
        return ""
    size = float(num_bytes)
    prefix = "≈" if approx else ""
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            if unit == "Б":
                return f"{prefix}{int(size)} {unit}"
            return f"{prefix}{size:.1f} {unit}"
        size /= 1024
    return f"{prefix}{size:.1f} ГБ"


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

    lines.append("\nВыберите разрешение для скачивания:")
    return "\n".join(lines)


def render_progress_bar(fraction: float, width: int = 12) -> str:
    """Текстовый прогресс-бар из блочных символов, например
    '████████░░░░' для fraction=0.66."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled)


def format_download_progress(height: int, fraction: float | None, label: str) -> str:
    """Текст статусного сообщения во время скачивания.

    label — что сейчас происходит: "видео"/"аудио" (какая дорожка качается)
    или "обработка" (склейка видео+аудио через ffmpeg, для неё yt-dlp не
    сообщает процент). fraction=None — доля неизвестна (например, yt-dlp не
    знает общий размер потока или ещё не показывает процент).
    """
    if label == "обработка":
        return f"🔧 Собираю файл {height}p, ещё немного..."
    if fraction is None:
        return f"⏳ Скачиваю {height}p ({label})..."
    percent = round(fraction * 100)
    bar = render_progress_bar(fraction)
    return f"⏳ Скачиваю {height}p ({label})\n{bar} {percent}%"


def format_history_entry(
    *,
    title: str | None,
    video_id: str | None,
    height: int | None,
    file_size_bytes: int | None,
    created_at: dt.datetime,
) -> str:
    """Одна строка для команды /history.

    file_size_bytes здесь — РЕАЛЬНЫЙ размер скачанного файла (записан в
    Event после успешной отправки), а не оценка с кнопок разрешений,
    поэтому format_size зовётся с approx=False — без "≈".
    """
    label = escape(title) if title else "Видео"
    if video_id:
        label = f'<a href="https://youtu.be/{video_id}">{label}</a>'

    parts = []
    if height:
        parts.append(f"{height}p")
    size_label = format_size(file_size_bytes, approx=False)
    if size_label:
        parts.append(size_label)
    parts.append(created_at.strftime("%d.%m %H:%M UTC"))

    return f"• {label}\n  {' · '.join(parts)}"
