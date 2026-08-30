from bot.commands import PUBLIC_COMMANDS


def test_public_commands_include_expected_set():
    names = {c.command for c in PUBLIC_COMMANDS}
    assert names == {"start", "help", "limits", "history", "cancel", "terms", "feedback"}


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

    bot.set_my_commands.assert_awaited_once_with(PUBLIC_COMMANDS)


async def test_set_bot_commands_sets_per_admin_chat_scope_with_admin_commands():
    bot = _make_bot()
    config = _make_config(frozenset({111}))

    await set_bot_commands(bot, config)

    assert bot.set_my_commands.await_count == 2  # дефолт + один админ
    admin_call = bot.set_my_commands.await_args_list[1]
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

    # дефолт + оба админа — оба вызова были СДЕЛАНЫ, даже если один упал
    assert bot.set_my_commands.await_count == 3
    called_chat_ids = {
        call.kwargs["scope"].chat_id
        for call in bot.set_my_commands.await_args_list
        if call.kwargs.get("scope") is not None
    }
    assert called_chat_ids == {999, 111}
