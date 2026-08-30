from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.formatting import format_size


def build_resolution_keyboard(
    request_id: str,
    heights: list[int],
    sizes: dict[int, int | None] | None = None,
) -> InlineKeyboardMarkup:
    sizes = sizes or {}
    builder = InlineKeyboardBuilder()
    for height in heights:
        size_label = format_size(sizes.get(height))
        text = f"{height}p · {size_label}" if size_label else f"{height}p"
        builder.button(text=text, callback_data=f"dl:{request_id}:{height}")
    # Размер тут намеренно не показываем (в отличие от кнопок разрешений
    # выше) — по просьбе пользователя кнопка должна быть простой "Скачать
    # аудио" без деталей.
    builder.button(text="🎵 Скачать аудио", callback_data=f"dla:{request_id}")
    builder.adjust(2)
    return builder.as_markup()
