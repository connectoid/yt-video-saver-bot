from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from bot.db import crud
from bot.db.engine import Database
from bot.db.models import EventStatus, Stage
from bot.handlers.feedback import FEEDBACK_PROMPT, FeedbackStates
from bot.middlewares.feedback_capture import FeedbackCaptureMiddleware, _notify_admins


# --- бд: feedback_today в /stats -------------------------------------------


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await database.create_all()
    yield database
    await database.close()


async def test_get_stats_counts_feedback_today(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")
    await crud.log_event(db, user_id=1, stage=Stage.FEEDBACK, status=EventStatus.SUCCESS)
    await crud.log_event(db, user_id=1, stage=Stage.FEEDBACK, status=EventStatus.SUCCESS)
    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.FAILED_ERROR, height=480)

    stats = await crud.get_stats(db)

    assert stats.feedback_today == 2
    # FEEDBACK — не сбой, не должен попадать в "провалы по причинам"
    assert Stage.FEEDBACK not in stats.failures_today_by_status
    assert stats.failures_today_by_status[EventStatus.FAILED_ERROR] == 1


# --- содержимое приглашения / состояния -------------------------------------


def test_feedback_prompt_mentions_cancel():
    assert "/cancel" in FEEDBACK_PROMPT


def test_feedback_prompt_is_non_empty_and_reasonable_length():
    assert 0 < len(FEEDBACK_PROMPT) <= 1000


def test_feedback_states_has_single_waiting_state():
    assert FeedbackStates.waiting_for_message.state == "FeedbackStates:waiting_for_message"


# --- вспомогалки для мок-сообщений -------------------------------------------


def make_event(text=None, username="alex", full_name="Alex", user_id=42):
    event = MagicMock(spec=Message)
    event.from_user = SimpleNamespace(id=user_id, username=username, full_name=full_name)
    event.text = text
    event.bot = MagicMock()
    event.bot.send_message = AsyncMock()
    event.forward = AsyncMock()
    event.answer = AsyncMock()
    return event


def make_config(admin_user_ids):
    return SimpleNamespace(admin_user_ids=admin_user_ids)


# --- _notify_admins -----------------------------------------------------------


async def test_notify_admins_uses_username_mention():
    event = make_event(username="alex", full_name="Alex")
    config = make_config([100])

    await _notify_admins(event, config)

    prefix = event.bot.send_message.call_args.args[1]
    assert "@alex" in prefix
    assert 'tg://user?id=42' in prefix
    event.forward.assert_awaited_once_with(100)


async def test_notify_admins_falls_back_to_full_name_when_no_username():
    event = make_event(username=None, full_name="Sasha B")
    config = make_config([100])

    await _notify_admins(event, config)

    prefix = event.bot.send_message.call_args.args[1]
    assert "Sasha B" in prefix


async def test_notify_admins_escapes_html_special_chars_in_full_name():
    event = make_event(username=None, full_name="<script>alert(1)</script>")
    config = make_config([100])

    await _notify_admins(event, config)

    prefix = event.bot.send_message.call_args.args[1]
    assert "<script>" not in prefix
    assert "&lt;script&gt;" in prefix


async def test_notify_admins_sends_to_every_admin():
    event = make_event()
    config = make_config([100, 200, 300])

    await _notify_admins(event, config)

    assert event.bot.send_message.await_count == 3
    assert event.forward.await_count == 3
    forwarded_to = [call.args[0] for call in event.forward.await_args_list]
    assert forwarded_to == [100, 200, 300]


async def test_notify_admins_continues_when_one_admin_fails():
    event = make_event()
    config = make_config([100, 200])
    event.bot.send_message.side_effect = [RuntimeError("blocked bot"), None]

    await _notify_admins(event, config)

    assert event.bot.send_message.await_count == 2
    # форвард должен уйти хотя бы второму админу, несмотря на сбой у первого
    assert event.forward.await_count >= 1


# --- FeedbackCaptureMiddleware: маршрутизация --------------------------------


def make_state(current_state):
    state = MagicMock()
    state.get_state = AsyncMock(return_value=current_state)
    state.clear = AsyncMock()
    return state


async def test_middleware_passes_through_non_message_events():
    middleware = FeedbackCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = object()  # заведомо не Message

    result = await middleware(handler, event, {})

    assert result == "handled"
    handler.assert_awaited_once_with(event, {})


async def test_middleware_passes_through_when_no_state_in_data():
    middleware = FeedbackCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="hello")

    result = await middleware(handler, event, {})

    assert result == "handled"
    handler.assert_awaited_once()


async def test_middleware_passes_through_when_not_waiting_for_feedback():
    middleware = FeedbackCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="https://youtu.be/dQw4w9WgXcQ")
    state = make_state(None)

    result = await middleware(handler, event, {"state": state})

    assert result == "handled"
    handler.assert_awaited_once()
    state.clear.assert_not_awaited()


async def test_middleware_command_clears_state_and_falls_through_to_handler():
    middleware = FeedbackCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="/cancel")
    state = make_state(FeedbackStates.waiting_for_message.state)

    result = await middleware(handler, event, {"state": state})

    assert result == "handled"
    state.clear.assert_awaited_once()
    handler.assert_awaited_once()
    event.bot.send_message.assert_not_awaited()  # фидбек не должен был уйти


async def test_middleware_captures_text_message_and_logs_event(db):
    middleware = FeedbackCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="у бота баг: не скачивается плейлист", user_id=7)
    state = make_state(FeedbackStates.waiting_for_message.state)
    config = make_config([100])
    await crud.get_or_create_user(db, 7, "alex", "Alex")

    result = await middleware(handler, event, {"state": state, "config": config, "db": db})

    assert result is None
    handler.assert_not_awaited()  # перехвачено, до обычных хендлеров не дошло
    state.clear.assert_awaited_once()
    event.bot.send_message.assert_awaited_once()
    event.forward.assert_awaited_once_with(100)
    event.answer.assert_awaited_once()

    stats = await crud.get_stats(db)
    assert stats.feedback_today == 1


async def test_middleware_captures_non_text_message_like_photo():
    middleware = FeedbackCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text=None)  # например, фото без подписи
    state = make_state(FeedbackStates.waiting_for_message.state)
    config = make_config([100])

    result = await middleware(handler, event, {"state": state, "config": config, "db": None})

    assert result is None
    handler.assert_not_awaited()
    event.forward.assert_awaited_once_with(100)


async def test_middleware_warns_when_no_admins_configured():
    middleware = FeedbackCaptureMiddleware()
    handler = AsyncMock(return_value="handled")
    event = make_event(text="привет")
    state = make_state(FeedbackStates.waiting_for_message.state)
    config = make_config(frozenset())

    result = await middleware(handler, event, {"state": state, "config": config})

    assert result is None
    handler.assert_not_awaited()
    event.bot.send_message.assert_not_awaited()
    event.forward.assert_not_awaited()
    event.answer.assert_awaited_once()
    warning_text = event.answer.call_args.args[0]
    assert "не настроен" in warning_text
