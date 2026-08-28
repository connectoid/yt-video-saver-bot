from __future__ import annotations

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
