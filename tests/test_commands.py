from bot.commands import PUBLIC_COMMANDS


def test_public_commands_include_expected_set():
    names = {c.command for c in PUBLIC_COMMANDS}
    assert names == {"start", "help", "limits", "history", "cancel"}


def test_public_commands_exclude_admin_only_stats():
    # /stats — админ-команда, admin.py молча игнорирует её для не-админов,
    # чтобы не выдавать сам факт её существования. Попадание в публичное
    # меню бота это бы перечеркнуло.
    names = {c.command for c in PUBLIC_COMMANDS}
    assert "stats" not in names


def test_public_commands_have_non_empty_descriptions():
    for command in PUBLIC_COMMANDS:
        assert command.description.strip()
