from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import Config
from bot.i18n import t
from bot.utils.formatting import build_terms_text, format_file_limit_note

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, lang: str) -> None:
    await message.answer(t(lang, "welcome"))


@router.message(Command("help"))
async def cmd_help(message: Message, config: Config, lang: str) -> None:
    await message.answer(t(lang, "help_header") + format_file_limit_note(config, lang))


@router.message(Command("terms"))
async def cmd_terms(message: Message, config: Config, lang: str) -> None:
    await message.answer(build_terms_text(config.support_contact, lang))
