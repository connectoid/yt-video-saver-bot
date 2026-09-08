from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.db import crud
from bot.db.engine import Database
from bot.handlers.broadcast import (
    BroadcastStates,
    cmd_broadcast,
    confirm_keyboard,
    handle_broadcast_cancel,
    handle_broadcast_confirm,
)
from bot.middlewares.broadcast_capture import BroadcastCaptureMiddleware
from bot.services import broadcast_service
from bot.services.broadcast_service import BroadcastResult, send_broadcast


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await database.create_all()
    yield database
    await database.close()


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    # Тесты не должны реально ждать SEND_INTERVAL_SECONDS между отправками.
    monkeypatch.setattr(broadcast_service, "SEND_INTERVAL_SECONDS", 0)


# --- crud.list_users_for_broadcast ------------------------------------------


async def test_list_users_for_broadcast_returns_id_language_code_and_ui_language(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex", language_code="ru")
    await crud.get_or_create_user(db, 2, "sam", "Sam", language_code="en")
    await crud.set_ui_language(db, 2, "ru")

    users = await crud.list_users_for_broadcast(db)

    assert set(users) == {(1, "ru", None), (2, "en", "ru")}


async def test_list_users_for_broadcast_empty_db(db):
    assert await crud.list_users_for_broadcast(db) == []


# --- send_broadcast ----------------------------------------------------------


async def test_send_broadcast_routes_each_user_to_their_resolved_language(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex", language_code="ru")
    await crud.get_or_create_user(db, 2, "sam", "Sam", language_code="en")
    await crud.get_or_create_user(db, 3, "kim", "Kim", language_code="fr")  # -> DEFAULT ("en")
    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await send_broadcast(bot, db, "Привет", "Hello")

    assert result == BroadcastResult(total=3, sent=3, failed=0)
    sent_texts = {call.args[0]: call.args[1] for call in bot.send_message.await_args_list}
    assert sent_texts == {1: "Привет", 2: "Hello", 3: "Hello"}


async def test_send_broadcast_ui_language_overrides_telegram_language_code(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex", language_code="en")
    await crud.set_ui_language(db, 1, "ru")
    bot = MagicMock()
    bot.send_message = AsyncMock()

    await send_broadcast(bot, db, "Привет", "Hello")

    bot.send_message.assert_awaited_once_with(1, "Привет")


async def test_send_broadcast_counts_failures_and_continues(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex", language_code="ru")
    await crud.get_or_create_user(db, 2, "sam", "Sam", language_code="ru")
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[RuntimeError("bot was blocked by the user"), None])

    result = await send_broadcast(bot, db, "Привет", "Hello")

    assert result == BroadcastResult(total=2, sent=1, failed=1)
    assert bot.send_message.await_count == 2


async def test_send_broadcast_empty_user_list(db):
    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await send_broadcast(bot, db, "Привет", "Hello")

    assert result == BroadcastResult(total=0, sent=0, failed=0)
    bot.send_message.assert_not_awaited()


# --- BroadcastStates / confirm_keyboard --------------------------------------


def test_broadcast_states_are_three_distinct_states():
    assert BroadcastStates.waiting_for_ru.state == "BroadcastStates:waiting_for_ru"
    assert BroadcastStates.waiting_for_en.state == "BroadcastStates:waiting_for_en"
    assert BroadcastStates.confirming.state == "BroadcastStates:confirming"


def test_confirm_keyboard_has_confirm_and_cancel_callbacks():
    keyboard = confirm_keyboard()
    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "broadcast:confirm" in callback_data
    assert "broadcast:cancel" in callback_data


# --- cmd_broadcast -------------------------------------------------------------


def make_message(user_id=1):
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=user_id)
    message.answer = AsyncMock()
    return message


def make_state(current_state=None):
    state = MagicMock()
    state.get_state = AsyncMock(return_value=current_state)
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def make_config(admin_ids):
    return SimpleNamespace(admin_user_ids=set(admin_ids), is_admin=lambda uid: uid in admin_ids)


async def test_cmd_broadcast_ignores_non_admin():
    message = make_message(user_id=999)
    state = make_state()
    config = make_config([1])

    await cmd_broadcast(message, state, config)

    state.set_state.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_cmd_broadcast_prompts_admin_for_russian_text():
    message = make_message(user_id=1)
    state = make_state()
    config = make_config([1])

    await cmd_broadcast(message, state, config)

    state.set_state.assert_awaited_once_with(BroadcastStates.waiting_for_ru)
    message.answer.assert_awaited_once()


# --- handle_broadcast_confirm / handle_broadcast_cancel -----------------------


def make_callback(user_id=1):
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=user_id)
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.bot = MagicMock()
    return callback


async def test_handle_broadcast_confirm_ignores_non_admin():
    callback = make_callback(user_id=999)
    state = make_state(BroadcastStates.confirming.state)
    config = make_config([1])

    await handle_broadcast_confirm(callback, state, config, db=MagicMock())

    state.clear.assert_not_awaited()
    callback.answer.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()


async def test_handle_broadcast_confirm_stale_state_does_nothing(db):
    callback = make_callback(user_id=1)
    state = make_state(BroadcastStates.waiting_for_en.state)  # ещё не подтверждающий шаг
    config = make_config([1])

    await handle_broadcast_confirm(callback, state, config, db=db)

    state.clear.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


async def test_handle_broadcast_confirm_launches_background_broadcast(db, monkeypatch):
    await crud.get_or_create_user(db, 5, "alex", "Alex", language_code="ru")
    callback = make_callback(user_id=1)
    state = make_state(BroadcastStates.confirming.state)
    state.get_data = AsyncMock(return_value={"broadcast_ru": "Привет", "broadcast_en": "Hello"})
    config = make_config([1])

    captured = {}

    def fake_create_task(coro):
        captured["coro"] = coro
        coro.close()  # не запускаем реально в фоне — просто проверяем, что задача создана
        return MagicMock()

    monkeypatch.setattr("bot.handlers.broadcast.asyncio.create_task", fake_create_task)

    await handle_broadcast_confirm(callback, state, config, db=db)

    state.clear.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()
    assert "coro" in captured


async def test_handle_broadcast_cancel_clears_state_and_edits_message():
    callback = make_callback(user_id=1)
    state = make_state(BroadcastStates.waiting_for_ru.state)
    config = make_config([1])

    await handle_broadcast_cancel(callback, state, config)

    state.clear.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()


# --- BroadcastCaptureMiddleware ------------------------------------------------


def make_event(text=None, html_text=None, user_id=1):
    event = MagicMock(spec=Message)
    event.from_user = SimpleNamespace(id=user_id)
    event.text = text
    event.html_text = html_text if html_text is not None else text
    event.answer = AsyncMock()
    return event


def make_mw_state(current_state):
    state = MagicMock()
    state.get_state = AsyncMock(return_value=current_state)
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={"broadcast_ru": "Привет"})
    return state


async def test_broadcast_mw_passes_through_non_message_events():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")

    result = await middleware(handler, object(), {})

    assert result == "handled"
    handler.assert_awaited_once()


async def test_broadcast_mw_passes_through_when_not_in_broadcast_state():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="hello")
    state = make_mw_state(None)

    result = await middleware(handler, event, {"state": state})

    assert result == "handled"
    state.clear.assert_not_awaited()


async def test_broadcast_mw_clears_state_for_non_admin():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="some text", user_id=999)
    state = make_mw_state(BroadcastStates.waiting_for_ru.state)
    config = make_config([1])

    result = await middleware(handler, event, {"state": state, "config": config})

    assert result == "handled"
    state.clear.assert_awaited_once()


async def test_broadcast_mw_command_clears_state_and_falls_through():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="/cancel", user_id=1)
    state = make_mw_state(BroadcastStates.waiting_for_ru.state)
    config = make_config([1])

    result = await middleware(handler, event, {"state": state, "config": config})

    assert result == "handled"
    state.clear.assert_awaited_once()


async def test_broadcast_mw_rejects_empty_text():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="   ", html_text="   ", user_id=1)
    state = make_mw_state(BroadcastStates.waiting_for_ru.state)
    config = make_config([1])

    result = await middleware(handler, event, {"state": state, "config": config})

    assert result is None
    handler.assert_not_awaited()
    event.answer.assert_awaited_once()


async def test_broadcast_mw_captures_ru_text_and_moves_to_waiting_for_en():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="Всем привет", user_id=1)
    state = make_mw_state(BroadcastStates.waiting_for_ru.state)
    config = make_config([1])

    result = await middleware(handler, event, {"state": state, "config": config})

    assert result is None
    handler.assert_not_awaited()
    state.update_data.assert_awaited_once_with(broadcast_ru="Всем привет")
    state.set_state.assert_awaited_once_with(BroadcastStates.waiting_for_en)
    event.answer.assert_awaited_once()


async def test_broadcast_mw_captures_en_text_and_shows_preview_with_keyboard():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="Hi everyone", user_id=1)
    state = make_mw_state(BroadcastStates.waiting_for_en.state)
    config = make_config([1])

    result = await middleware(handler, event, {"state": state, "config": config})

    assert result is None
    state.update_data.assert_awaited_once_with(broadcast_en="Hi everyone")
    state.set_state.assert_awaited_once_with(BroadcastStates.confirming)
    event.answer.assert_awaited_once()
    preview_text = event.answer.call_args.args[0]
    assert "Привет" in preview_text  # broadcast_ru из state.get_data()
    assert "Hi everyone" in preview_text
    assert event.answer.call_args.kwargs["reply_markup"] is not None


async def test_broadcast_mw_preserves_html_formatting_via_html_text():
    middleware = BroadcastCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="bold text", html_text="<b>bold</b> text", user_id=1)
    state = make_mw_state(BroadcastStates.waiting_for_ru.state)
    config = make_config([1])

    await middleware(handler, event, {"state": state, "config": config})

    state.update_data.assert_awaited_once_with(broadcast_ru="<b>bold</b> text")
