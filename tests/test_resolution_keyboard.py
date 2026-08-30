from bot.keyboards.resolution import build_resolution_keyboard


def _flat_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_audio_button_is_always_added():
    markup = build_resolution_keyboard("req1", [1080, 720], sizes={1080: 50_000_000})
    buttons = _flat_buttons(markup)
    audio_buttons = [b for b in buttons if b.callback_data == "dla:req1"]
    assert len(audio_buttons) == 1


def test_audio_button_text_has_no_size_or_format_details():
    # По просьбе пользователя — просто "Скачать аудио", без деталей вроде
    # размера или формата (в отличие от кнопок разрешений).
    markup = build_resolution_keyboard("req1", [1080], sizes={1080: 50_000_000})
    audio_button = next(b for b in _flat_buttons(markup) if b.callback_data == "dla:req1")
    assert audio_button.text == "🎵 Скачать аудио"


def test_resolution_buttons_unaffected_by_audio_button():
    markup = build_resolution_keyboard("req1", [1080, 720], sizes={1080: 50_000_000, 720: None})
    buttons = _flat_buttons(markup)
    resolution_buttons = [b for b in buttons if b.callback_data.startswith("dl:")]
    assert len(resolution_buttons) == 2
    assert resolution_buttons[0].callback_data == "dl:req1:1080"
    assert resolution_buttons[1].callback_data == "dl:req1:720"
