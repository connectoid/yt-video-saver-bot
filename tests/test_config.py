from pathlib import Path

from bot.config import Config


def _make_config(admin_ids, daily_limit=5):
    return Config(
        bot_token="test-token",
        max_concurrent_downloads=3,
        downloads_dir=Path("/tmp"),
        log_level="INFO",
        max_file_size_mb=50,
        database_url="sqlite+aiosqlite:///:memory:",
        daily_download_limit=daily_limit,
        admin_user_ids=admin_ids,
        telegram_api_base_url=None,
    )


def test_is_admin_true_for_listed_id():
    config = _make_config(frozenset({111, 222}))
    assert config.is_admin(111) is True
    assert config.is_admin(222) is True


def test_is_admin_false_for_unlisted_id():
    config = _make_config(frozenset({111}))
    assert config.is_admin(999) is False


def test_is_admin_false_when_no_admins_configured():
    config = _make_config(frozenset())
    assert config.is_admin(111) is False
