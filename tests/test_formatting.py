from bot.utils.formatting import format_size


def test_format_size_megabytes():
    assert format_size(45_000_000) == "≈42.9 МБ"


def test_format_size_gigabytes():
    assert format_size(2_147_483_648) == "≈2.0 ГБ"


def test_format_size_bytes():
    assert format_size(500) == "≈500 Б"


def test_format_size_none_is_empty():
    assert format_size(None) == ""


def test_format_size_zero_is_empty():
    assert format_size(0) == ""


def test_format_size_without_approx_prefix():
    assert format_size(45_000_000, approx=False) == "42.9 МБ"
