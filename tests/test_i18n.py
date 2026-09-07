from bot.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TRANSLATIONS, resolve_language, t


def test_default_language_is_english():
    # См. bot/i18n.py: Stats.non_ru_users (bot/db/crud.py::get_stats)
    # показал ~90% пользователей с языком клиента Telegram не "ru".
    assert DEFAULT_LANGUAGE == "en"


def test_supported_languages_are_ru_and_en():
    assert set(SUPPORTED_LANGUAGES) == {"ru", "en"}


def test_translation_tables_have_matching_keys():
    # Ключи должны совпадать построчно между языками — иначе t() будет
    # тихо фолбэкать на DEFAULT_LANGUAGE для случайно забытого перевода
    # (см. t() ниже), что легко не заметить в чате.
    ru_keys = set(TRANSLATIONS["ru"])
    en_keys = set(TRANSLATIONS["en"])
    assert ru_keys == en_keys


def test_t_returns_requested_language():
    assert t("ru", "audio_button") == "🎵 Скачать аудио"
    assert t("en", "audio_button") == "🎵 Download audio"


def test_t_falls_back_to_default_language_for_unknown_lang():
    assert t("fr", "audio_button") == t(DEFAULT_LANGUAGE, "audio_button")


def test_t_returns_key_itself_for_unknown_key():
    assert t("en", "totally_made_up_key") == "totally_made_up_key"


def test_t_formats_placeholders():
    text = t("en", "queue_position", ahead=3)
    assert "3" in text


def test_resolve_language_prefers_explicit_ui_language():
    assert resolve_language("ru", "en") == "en"
    assert resolve_language(None, "ru") == "ru"


def test_resolve_language_falls_back_to_telegram_language_code():
    assert resolve_language("ru", None) == "ru"
    assert resolve_language("ru-RU", None) == "ru"


def test_resolve_language_defaults_to_english_for_unknown_or_missing():
    assert resolve_language(None, None) == "en"
    assert resolve_language("fr", None) == "en"
    assert resolve_language("uk", None) == "en"


def test_resolve_language_ignores_unsupported_ui_language():
    # ui_language в БД в теории могло бы содержать мусор — не должно
    # уронить резолвинг, просто игнорируем и идём дальше по приоритету.
    assert resolve_language("ru", "fr") == "ru"
    assert resolve_language(None, "fr") == "en"
