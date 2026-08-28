from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_resolution_keyboard(request_id: str, heights: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for height in heights:
        builder.button(text=f"{height}p", callback_data=f"dl:{request_id}:{height}")
    builder.adjust(2)
    return builder.as_markup()
