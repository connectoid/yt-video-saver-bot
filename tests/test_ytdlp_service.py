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
