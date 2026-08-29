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
