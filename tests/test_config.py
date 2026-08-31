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


def _write_env(tmp_path, extra_lines=""):
    env_path = tmp_path / ".env"
    env_path.write_text(f"BOT_TOKEN=test-token\n{extra_lines}")
    return env_path


def test_cookies_file_defaults_to_none_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    from bot.config import load_config

    config = load_config(env_file=_write_env(tmp_path))
    assert config.cookies_file is None


def test_cookies_file_relative_path_resolved_against_base_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    from bot.config import BASE_DIR, load_config

    config = load_config(env_file=_write_env(tmp_path, "YTDLP_COOKIES_FILE=cookies.txt\n"))
    assert config.cookies_file == BASE_DIR / "cookies.txt"


def test_cookies_file_absolute_path_kept_as_is(tmp_path, monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    from bot.config import load_config

    absolute = tmp_path / "somewhere" / "cookies.txt"
    config = load_config(env_file=_write_env(tmp_path, f"YTDLP_COOKIES_FILE={absolute}\n"))
    assert config.cookies_file == absolute
