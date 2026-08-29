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


import datetime as dt

from bot.utils.formatting import format_history_entry


def test_format_history_entry_with_title_and_link():
    text = format_history_entry(
        title="Cool Video",
        video_id="abc123",
        height=720,
        file_size_bytes=45_000_000,
        created_at=dt.datetime(2026, 8, 29, 14, 3, tzinfo=dt.timezone.utc),
    )
    assert '<a href="https://youtu.be/abc123">Cool Video</a>' in text
    assert "720p" in text
    assert "42.9 МБ" in text and "≈" not in text  # реальный размер, не оценка
    assert "29.08 14:03 UTC" in text


def test_format_history_entry_escapes_title():
    text = format_history_entry(
        title="<script>alert(1)</script>",
        video_id="abc123",
        height=720,
        file_size_bytes=1000,
        created_at=dt.datetime(2026, 8, 29, 14, 3, tzinfo=dt.timezone.utc),
    )
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_format_history_entry_missing_title_falls_back():
    text = format_history_entry(
        title=None,
        video_id="abc123",
        height=720,
        file_size_bytes=1000,
        created_at=dt.datetime(2026, 8, 29, 14, 3, tzinfo=dt.timezone.utc),
    )
    assert "Видео" in text


def test_format_history_entry_missing_video_id_no_link():
    text = format_history_entry(
        title="Cool",
        video_id=None,
        height=720,
        file_size_bytes=1000,
        created_at=dt.datetime(2026, 8, 29, 14, 3, tzinfo=dt.timezone.utc),
    )
    assert "<a href" not in text
    assert "Cool" in text


from bot.utils.formatting import build_terms_text


def test_build_terms_text_with_support_contact():
    text = build_terms_text("@support_user")
    assert "@support_user" in text
    assert "/terms" in text


def test_build_terms_text_without_support_contact_uses_generic_line():
    text = build_terms_text(None)
    assert "администратору" in text


def test_build_terms_text_mentions_blocking_by_rightsholder_request():
    text = build_terms_text(None)
    assert "правообладателя" in text
