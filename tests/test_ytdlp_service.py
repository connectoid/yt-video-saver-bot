from bot.services.ytdlp_service import _select_offered_heights


def test_standard_ladder_keeps_top_four():
    heights = [2160, 1440, 1080, 720, 480, 360, 240, 144]
    assert _select_offered_heights(heights) == [1080, 720, 480, 360]


def test_single_height_available():
    assert _select_offered_heights([1080]) == [1080]


def test_nonstandard_heights_are_bucketed():
    # YouTube иногда отдаёт нестандартные значения высоты (например, из-за
    # урезанного набора форматов) — раньше это давало только одну кнопку,
    # хотя реальных вариантов было несколько.
    heights = [1080, 894, 638, 240]
    assert _select_offered_heights(heights) == [1080, 894, 638, 240]


def test_sparse_ladder_missing_some_tiers():
    heights = [1080, 360]
    assert _select_offered_heights(heights) == [1080, 360]


def test_only_low_resolutions_available():
    heights = [240, 144]
    assert _select_offered_heights(heights) == [240, 144]


def test_empty_input():
    assert _select_offered_heights([]) == []


def test_4k_does_not_crowd_out_1080p():
    # h=2160/1440 удовлетворяют "h >= 1080", но не должны занимать слот 1080p.
    heights = [2160, 1440, 1080, 720, 480, 360, 240, 144]
    assert _select_offered_heights(heights) == [1080, 720, 480, 360]


def test_only_above_cap_falls_back_to_best():
    assert _select_offered_heights([2160, 1440]) == [2160]


from bot.services.ytdlp_service import _build_format_selector


def test_format_selector_has_exact_height_tiers_first():
    selector = _build_format_selector(720)
    tiers = selector.split("/")
    assert tiers[0] == "bestvideo[height=720][ext=mp4]+bestaudio[ext=m4a]"
    assert tiers[1] == "bestvideo[height=720]+bestaudio"
    assert tiers[2] == "best[height=720]"


def test_format_selector_has_fallback_tiers_so_it_never_hard_fails():
    # Регрессия: прод-баг 2026-08-31 (ERROR: Requested format is not
    # available) — кнопка обещала высоту, доступную при показе кнопок,
    # но к моменту фактического скачивания YouTube эту высоту не отдал
    # (client-специфичное поведение). Без catch-all в конце пользователь
    # получал жёсткий отказ вместо видео похожего качества.
    selector = _build_format_selector(720)
    tiers = selector.split("/")
    assert tiers[3] == "best[height<=720]"
    assert tiers[4] == "best"
    assert tiers[-1] == "best"  # действительно безусловный катч-олл в конце


from bot.services.ytdlp_service import _best_audio_size_bytes, _estimate_size_bytes


def _video_only(height, ext, size=None, size_approx=None):
    fmt = {"height": height, "vcodec": "avc1.640028", "acodec": "none", "ext": ext}
    if size is not None:
        fmt["filesize"] = size
    if size_approx is not None:
        fmt["filesize_approx"] = size_approx
    return fmt


def _audio_only(ext, abr, size=None):
    fmt = {"vcodec": "none", "acodec": "mp4a.40.2", "ext": ext, "abr": abr}
    if size is not None:
        fmt["filesize"] = size
    return fmt


def _progressive(height, ext, size=None):
    fmt = {"height": height, "vcodec": "avc1.640028", "acodec": "mp4a.40.2", "ext": ext}
    if size is not None:
        fmt["filesize"] = size
    return fmt


def test_estimate_size_adds_video_and_best_audio():
    formats = [
        _video_only(720, "mp4", size=40_000_000),
        _audio_only("webm", abr=128, size=3_000_000),
        _audio_only("m4a", abr=128, size=3_200_000),
    ]
    # m4a должен быть выбран как лучшее аудио (приоритет ext=m4a), несмотря
    # на одинаковый abr с webm-дорожкой.
    assert _estimate_size_bytes(formats, 720) == 40_000_000 + 3_200_000


def test_estimate_size_falls_back_to_filesize_approx():
    formats = [
        _video_only(480, "mp4", size_approx=20_000_000),
        _audio_only("m4a", abr=128, size=2_500_000),
    ]
    assert _estimate_size_bytes(formats, 480) == 20_000_000 + 2_500_000


def test_estimate_size_uses_progressive_without_double_counting_audio():
    formats = [
        _progressive(360, "mp4", size=15_000_000),
        _audio_only("m4a", abr=128, size=2_000_000),
    ]
    # Прогрессивный поток уже содержит звук — размер аудио не должен
    # прибавляться повторно.
    assert _estimate_size_bytes(formats, 360) == 15_000_000


def test_estimate_size_returns_none_without_data():
    formats = [{"height": 720, "vcodec": "avc1.640028", "acodec": "none", "ext": "mp4"}]
    assert _estimate_size_bytes(formats, 720) is None


def test_estimate_size_returns_none_for_missing_height():
    formats = [_video_only(720, "mp4", size=40_000_000)]
    assert _estimate_size_bytes(formats, 1080) is None


def test_best_audio_size_prefers_m4a():
    formats = [
        _audio_only("webm", abr=160, size=4_000_000),
        _audio_only("m4a", abr=128, size=3_200_000),
    ]
    assert _best_audio_size_bytes(formats) == 3_200_000


def test_best_audio_size_none_without_audio_formats():
    formats = [_video_only(720, "mp4", size=40_000_000)]
    assert _best_audio_size_bytes(formats) is None


from bot.services.ytdlp_service import _make_postprocessor_hook, _make_progress_hook, _stream_label


def test_stream_label_video_only():
    assert _stream_label({"vcodec": "avc1", "acodec": "none"}) == "видео"


def test_stream_label_audio_only():
    assert _stream_label({"vcodec": "none", "acodec": "m4a"}) == "аудио"


def test_stream_label_progressive_counts_as_video():
    assert _stream_label({"vcodec": "avc1", "acodec": "m4a"}) == "видео"


def test_progress_hook_reports_fraction_from_downloaded_and_total():
    calls = []
    hook = _make_progress_hook(lambda fraction, label: calls.append((fraction, label)), None)

    hook({
        "status": "downloading",
        "downloaded_bytes": 50,
        "total_bytes": 200,
        "info_dict": {"vcodec": "avc1", "acodec": "none"},
    })

    assert calls == [(0.25, "видео")]


def test_progress_hook_falls_back_to_estimate_when_total_missing():
    calls = []
    hook = _make_progress_hook(lambda fraction, label: calls.append((fraction, label)), None)

    hook({
        "status": "downloading",
        "downloaded_bytes": 10,
        "total_bytes_estimate": 40,
        "info_dict": {"vcodec": "none", "acodec": "m4a"},
    })

    assert calls == [(0.25, "аудио")]


def test_progress_hook_reports_none_when_total_unknown():
    calls = []
    hook = _make_progress_hook(lambda fraction, label: calls.append((fraction, label)), None)

    hook({
        "status": "downloading",
        "downloaded_bytes": 10,
        "info_dict": {"vcodec": "avc1", "acodec": "none"},
    })

    assert calls == [(None, "видео")]


def test_progress_hook_ignores_non_downloading_status_except_finished():
    calls = []
    hook = _make_progress_hook(lambda fraction, label: calls.append((fraction, label)), None)

    hook({"status": "error", "info_dict": {}})
    assert calls == []


def test_progress_hook_reports_full_on_finished():
    calls = []
    hook = _make_progress_hook(lambda fraction, label: calls.append((fraction, label)), None)

    hook({"status": "finished", "info_dict": {"vcodec": "avc1", "acodec": "none"}})

    assert calls == [(1.0, "видео")]


def test_postprocessor_hook_reports_processing_stage_on_start():
    calls = []
    hook = _make_postprocessor_hook(lambda fraction, label: calls.append((fraction, label)), None)

    hook({"status": "started"})

    assert calls == [(None, "обработка")]


def test_postprocessor_hook_ignores_finished():
    calls = []
    hook = _make_postprocessor_hook(lambda fraction, label: calls.append((fraction, label)), None)

    hook({"status": "finished"})

    assert calls == []


def test_estimate_size_prefers_yt_dlp_order_not_largest_file():
    # Регрессия: раньше среди нескольких кандидатов на одной высоте без
    # mp4-варианта выбирался просто самый ТЯЖЁЛЫЙ файл — это завышало
    # оценку, если yt-dlp в реальности выбирает более лёгкий (например,
    # AV1 вместо VP9 при том же качестве). yt-dlp отдаёт formats
    # отсортированными от худшего к лучшему по своему приоритету, поэтому
    # правильный ориентир — последний подходящий элемент в списке, а не
    # самый большой по размеру.
    formats = [
        {
            "height": 720, "vcodec": "vp09.00.21.08", "acodec": "none",
            "ext": "webm", "filesize": 60_000_000,
        },
        {
            # Идёт позже в списке => yt-dlp считает его предпочтительнее,
            # хотя по размеру он меньше.
            "height": 720, "vcodec": "av01.0.05M.08", "acodec": "none",
            "ext": "webm", "filesize": 35_000_000,
        },
        _audio_only("m4a", abr=128, size=3_200_000),
    ]
    assert _estimate_size_bytes(formats, 720) == 35_000_000 + 3_200_000


def test_estimate_size_mp4_still_wins_over_later_non_mp4():
    # mp4 остаётся приоритетным контейнером независимо от порядка — это
    # то, что реально просит _build_format_selector в первую очередь.
    formats = [
        _video_only(720, "mp4", size=32_000_000),
        {
            "height": 720, "vcodec": "vp09.00.21.08", "acodec": "none",
            "ext": "webm", "filesize": 60_000_000,
        },
        _audio_only("m4a", abr=128, size=3_200_000),
    ]
    assert _estimate_size_bytes(formats, 720) == 32_000_000 + 3_200_000


def test_best_audio_size_prefers_last_m4a_not_highest_bitrate():
    formats = [
        _audio_only("m4a", abr=48, size=1_000_000),
        _audio_only("m4a", abr=128, size=3_200_000),
    ]
    # Оба m4a — берём последний в списке (порядок yt-dlp), а не тот, что
    # с большим битрейтом/размером.
    assert _best_audio_size_bytes(formats) == 3_200_000


def test_best_audio_size_falls_back_to_last_non_m4a_when_no_m4a():
    formats = [
        _audio_only("webm", abr=160, size=5_000_000),
        _audio_only("opus", abr=96, size=2_000_000),
    ]
    assert _best_audio_size_bytes(formats) == 2_000_000


import threading

from yt_dlp.utils import DownloadCancelled


def test_progress_hook_raises_when_cancel_event_set():
    cancel_event = threading.Event()
    cancel_event.set()
    hook = _make_progress_hook(lambda fraction, label: None, cancel_event)

    try:
        hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10, "info_dict": {}})
        assert False, "expected DownloadCancelled"
    except DownloadCancelled:
        pass


def test_progress_hook_does_not_raise_when_cancel_event_not_set():
    cancel_event = threading.Event()
    calls = []
    hook = _make_progress_hook(lambda fraction, label: calls.append((fraction, label)), cancel_event)

    hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10, "info_dict": {}})

    assert calls == [(0.1, "видео")]


def test_postprocessor_hook_raises_when_cancel_event_set():
    cancel_event = threading.Event()
    cancel_event.set()
    hook = _make_postprocessor_hook(lambda fraction, label: None, cancel_event)

    try:
        hook({"status": "started"})
        assert False, "expected DownloadCancelled"
    except DownloadCancelled:
        pass


# --- Аудио-кнопка: без ffmpeg-склейки/перекодирования, лучшее качество ---

from unittest.mock import MagicMock, patch

from bot.services.ytdlp_service import AUDIO_FORMAT_SELECTOR, _download_sync


def test_audio_format_selector_is_bestaudio_no_container_preference():
    # Явно НЕ "bestaudio[ext=m4a]/..." — пользователь попросил именно
    # лучшее качество, без предпочтения контейнера ради совместимости.
    assert AUDIO_FORMAT_SELECTOR == "bestaudio/best"


def _mock_ydl_factory(captured_opts, filepath):
    def make(opts):
        captured_opts.append(opts)
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.__exit__.return_value = False
        ydl.extract_info.return_value = {
            "requested_downloads": [{"filepath": str(filepath)}]
        }
        return ydl

    return make


def test_download_sync_sets_merge_output_format_for_video(tmp_path):
    captured = []
    target = tmp_path / "video.mp4"
    with patch(
        "bot.services.ytdlp_service.YoutubeDL",
        side_effect=_mock_ydl_factory(captured, target),
    ):
        result = _download_sync("https://youtu.be/x", "bestvideo+bestaudio", tmp_path)

    assert captured[0]["merge_output_format"] == "mp4"
    assert result == target


def test_download_sync_omits_merge_output_format_for_audio(tmp_path):
    # Ключевая проверка фичи "Скачать аудио": без merge_output_format
    # yt-dlp не запускает ffmpeg на склейку/перекодирование — дорожка
    # уходит как есть (m4a/webm/opus — что там от YouTube).
    captured = []
    target = tmp_path / "audio.m4a"
    with patch(
        "bot.services.ytdlp_service.YoutubeDL",
        side_effect=_mock_ydl_factory(captured, target),
    ):
        result = _download_sync(
            "https://youtu.be/x",
            AUDIO_FORMAT_SELECTOR,
            tmp_path,
            merge_output_format=None,
        )

    assert "merge_output_format" not in captured[0]
    assert result == target


def test_download_sync_without_cookies_tries_tv_client_first(tmp_path):
    # Без кук — бесплатная первая линия обхода (не гарантирует результат,
    # см. README), клиент tv куки всё равно бы проигнорировал.
    captured = []
    target = tmp_path / "video.mp4"
    with patch(
        "bot.services.ytdlp_service.YoutubeDL",
        side_effect=_mock_ydl_factory(captured, target),
    ):
        _download_sync("https://youtu.be/x", "bestvideo+bestaudio", tmp_path)

    clients = captured[0]["extractor_args"]["youtube"]["player_client"]
    assert clients[0] == "tv"
    assert "cookiefile" not in captured[0]


def test_download_sync_with_cookies_sets_cookiefile_and_skips_tv_client(tmp_path):
    # tv использует логин по коду устройства, а не cookie-jar — с куки
    # порядок клиентов меняется на web_safari/web, иначе кука просто не
    # применилась бы.
    captured = []
    target = tmp_path / "video.mp4"
    cookies_path = tmp_path / "cookies.txt"
    with patch(
        "bot.services.ytdlp_service.YoutubeDL",
        side_effect=_mock_ydl_factory(captured, target),
    ):
        _download_sync(
            "https://youtu.be/x", "bestvideo+bestaudio", tmp_path,
            cookies_file=cookies_path,
        )

    assert captured[0]["cookiefile"] == str(cookies_path)
    clients = captured[0]["extractor_args"]["youtube"]["player_client"]
    assert "tv" not in clients
    assert clients[0] == "web_safari"
