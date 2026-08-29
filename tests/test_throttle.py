from bot.utils.throttle import should_emit_progress


def test_first_update_always_emits():
    assert should_emit_progress(
        last_sent_at=None, last_fraction=None, last_label=None,
        now=100.0, fraction=0.1, label="видео",
    )


def test_label_change_emits_immediately():
    assert should_emit_progress(
        last_sent_at=100.0, last_fraction=0.9, last_label="видео",
        now=100.1, fraction=0.0, label="аудио",
    )


def test_completion_always_emits():
    assert should_emit_progress(
        last_sent_at=100.0, last_fraction=0.95, last_label="видео",
        now=100.1, fraction=1.0, label="видео",
    )


def test_throttled_when_too_soon_and_small_delta():
    assert not should_emit_progress(
        last_sent_at=100.0, last_fraction=0.20, last_label="видео",
        now=101.0, fraction=0.22, label="видео",
        min_interval=3.0, min_delta=0.05,
    )


def test_throttled_when_interval_ok_but_delta_too_small():
    assert not should_emit_progress(
        last_sent_at=100.0, last_fraction=0.20, last_label="видео",
        now=104.0, fraction=0.22, label="видео",
        min_interval=3.0, min_delta=0.05,
    )


def test_emits_when_interval_and_delta_both_ok():
    assert should_emit_progress(
        last_sent_at=100.0, last_fraction=0.20, last_label="видео",
        now=104.0, fraction=0.30, label="видео",
        min_interval=3.0, min_delta=0.05,
    )


def test_emits_when_fraction_unknown_and_interval_ok():
    assert should_emit_progress(
        last_sent_at=100.0, last_fraction=None, last_label="видео",
        now=104.0, fraction=None, label="видео",
        min_interval=3.0, min_delta=0.05,
    )
