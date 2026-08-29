from bot.profile import BOT_DESCRIPTION, BOT_NAME, BOT_SHORT_DESCRIPTION


def test_bot_name_within_api_limit():
    # Лимит Bot API для setMyName — 64 символа.
    assert len(BOT_NAME) <= 64
    assert BOT_NAME.strip() == BOT_NAME
    assert BOT_NAME


def test_bot_short_description_within_api_limit():
    # Лимит Bot API для setMyShortDescription — 120 символов.
    assert len(BOT_SHORT_DESCRIPTION) <= 120
    assert BOT_SHORT_DESCRIPTION


def test_bot_description_within_api_limit():
    # Лимит Bot API для setMyDescription — 512 символов.
    assert len(BOT_DESCRIPTION) <= 512
    assert BOT_DESCRIPTION


def test_bot_description_mentions_terms():
    assert "/terms" in BOT_DESCRIPTION
