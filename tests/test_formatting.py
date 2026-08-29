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


from bot.utils.formatting import format_download_progress, render_progress_bar


def test_render_progress_bar_partial():
    assert render_progress_bar(0.5, width=10) == "█████░░░░░"


def test_render_progress_bar_zero():
    assert render_progress_bar(0.0, width=10) == "░░░░░░░░░░"


def test_render_progress_bar_full():
    assert render_progress_bar(1.0, width=10) == "██████████"


def test_render_progress_bar_clamps_out_of_range():
    assert render_progress_bar(1.5, width=4) == "████"
    assert render_progress_bar(-0.2, width=4) == "░░░░"


def test_format_download_progress_with_fraction():
    text = format_download_progress(720, 0.5, "видео")
    assert "720p" in text
    assert "видео" in text
    assert "50%" in text


def test_format_download_progress_unknown_fraction():
    text = format_download_progress(720, None, "аудио")
    assert text == "⏳ Скачиваю 720p (аудио)..."


def test_format_download_progress_processing_stage():
    text = format_download_progress(720, None, "обработка")
    assert "Собираю файл 720p" in text
