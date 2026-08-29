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
