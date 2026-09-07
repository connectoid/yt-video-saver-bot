from bot.commands import PUBLIC_COMMANDS, PUBLIC_COMMANDS_EN


def test_public_commands_include_expected_set():
    names = {c.command for c in PUBLIC_COMMANDS}
    assert names == {
        "start", "help", "limits", "history", "cancel", "terms", "feedback", "language",
    }


def test_public_commands_en_has_same_command_set_as_ru():
    # Английский список — те же команды, что и русский (тот же порядок,
    # только описания на другом языке), см. bot/commands.py.
    ru_names = [c.command for c in PUBLIC_COMMANDS]
    en_names = [c.command for c in PUBLIC_COMMANDS_EN]
    assert ru_names == en_names


def test_public_commands_en_have_non_empty_descriptions():
    for command in PUBLIC_COMMANDS_EN:
        assert command.description.strip()


def test_public_commands_exclude_admin_only_commands():
    # /stats, /block, /unblock, /blocklist — админ-команды, admin.py молча
    # игнорирует их для не-админов, чтобы не выдавать сам факт их
    # существования. Попадание в публичное меню бота это бы перечеркнуло.
    names = {c.command for c in PUBLIC_COMMANDS}
    assert names.isdisjoint({"stats", "block", "unblock", "blocklist"})


def test_public_commands_have_non_empty_descriptions():
    for command in PUBLIC_COMMANDS:
        assert command.description.strip()


from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommandScopeChat

from bot.commands import ADMIN_COMMANDS, set_bot_commands
from bot.config import Config


def test_admin_commands_is_public_commands_plus_stats():
    public_names = [c.command for c in PUBLIC_COMMANDS]
    admin_names = [c.command for c in ADMIN_COMMANDS]

    assert admin_names == public_names + ["stats"]


def test_admin_commands_have_non_empty_descriptions():
    for command in ADMIN_COMMANDS:
        assert command.description.strip()


def _make_config(admin_ids):
    return Config(
        bot_token="test-token",
        max_concurrent_downloads=3,
        downloads_dir=Path("/tmp"),
        log_level="INFO",
        max_file_size_mb=50,
        database_url="sqlite+aiosqlite:///:memory:",
        daily_download_limit=5,
        admin_user_ids=admin_ids,
        telegram_api_base_url=None,
    )


def _make_bot(side_effect=None):
    bot = MagicMock(spec=Bot)
    bot.set_my_commands = AsyncMock(side_effect=side_effect, return_value=True)
    return bot


async def test_set_bot_commands_sets_default_scope_with_public_commands():
    bot = _make_bot()
    config = _make_config(frozenset())

    await set_bot_commands(bot, config)

    # Без админов — ровно два вызова на дефолтном скоупе: русский список
    # без language_code и английский с language_code="en" (см.
    # bot/commands.py::set_bot_commands).
    assert bot.set_my_commands.await_count == 2
    first_call, second_call = bot.set_my_commands.await_args_list
    assert first_call.args == (PUBLIC_COMMANDS,)
    assert not first_call.kwargs
    assert second_call.args == (PUBLIC_COMMANDS_EN,)
    assert second_call.kwargs == {"language_code": "en"}


async def test_set_bot_commands_sets_per_admin_chat_scope_with_admin_commands():
    bot = _make_bot()
    config = _make_config(frozenset({111}))

    await set_bot_commands(bot, config)

    # дефолт RU + дефолт EN + один админ
    assert bot.set_my_commands.await_count == 3
    admin_call = bot.set_my_commands.await_args_list[2]
    assert admin_call.args[0] == ADMIN_COMMANDS
    scope = admin_call.kwargs["scope"]
    assert isinstance(scope, BotCommandScopeChat)
    assert scope.chat_id == 111


async def test_set_bot_commands_one_admin_failure_does_not_block_others():
    # 999 — админ, ещё ни разу не писавший боту ("chat not found"); не
    # должен мешать применить меню остальным админам.
    def side_effect(commands, scope=None, **kwargs):
        if scope is not None and getattr(scope, "chat_id", None) == 999:
            raise TelegramBadRequest(method=MagicMock(), message="chat not found")
        return True

    bot = _make_bot(side_effect=side_effect)
    config = _make_config(frozenset({999, 111}))

    await set_bot_commands(bot, config)

    # дефолт RU + дефолт EN + оба админа — все вызовы были СДЕЛАНЫ, даже
    # если один упал
    assert bot.set_my_commands.await_count == 4
    called_chat_ids = {
        call.kwargs["scope"].chat_id
        for call in bot.set_my_commands.await_args_list
        if call.kwargs.get("scope") is not None
    }
    assert called_chat_ids == {999, 111}
