import datetime as dt

import pytest

from bot.db import crud
from bot.db.engine import Database
from bot.db.models import Event, EventStatus, Stage, User


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await database.create_all()
    yield database
    await database.close()


async def test_get_or_create_user_upserts(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex Original")
    await crud.get_or_create_user(db, 1, "alex_new", "Alex Renamed")

    async with db.session() as session:
        user = await session.get(User, 1)
        assert user is not None
        assert user.username == "alex_new"
        assert user.full_name == "Alex Renamed"


async def test_count_successful_downloads_today_filters_stage_and_status(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")

    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS, height=720)
    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS, height=480)
    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.FAILED_ERROR, height=1080)
    await crud.log_event(db, user_id=1, stage=Stage.INFO_FETCH, status=EventStatus.SUCCESS)

    count = await crud.count_successful_downloads_today(db, 1)
    assert count == 2


async def test_count_successful_downloads_today_ignores_yesterday(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")

    yesterday = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    async with db.session() as session:
        session.add(
            Event(user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS, created_at=yesterday)
        )
        await session.commit()

    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS)

    count = await crud.count_successful_downloads_today(db, 1)
    assert count == 1


async def test_get_stats_aggregates_correctly(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")
    await crud.get_or_create_user(db, 2, "bob", "Bob")

    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS, height=720)
    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.FAILED_SIZE_LIMIT, height=1080)
    await crud.log_event(db, user_id=2, stage=Stage.DOWNLOAD, status=EventStatus.FAILED_SIZE_LIMIT, height=1080)
    await crud.log_event(db, user_id=2, stage=Stage.DOWNLOAD, status=EventStatus.BLOCKED_DAILY_LIMIT)
    await crud.log_event(db, user_id=2, stage=Stage.INFO_FETCH, status=EventStatus.FAILED_UNAVAILABLE)

    stats = await crud.get_stats(db)

    assert stats.total_users == 2
    assert stats.new_users_today == 2
    assert stats.active_users_today == 2
    assert stats.downloads_success_today == 1
    assert stats.downloads_success_total == 1
    assert stats.blocked_by_limit_today == 1
    assert stats.failures_today_by_status[EventStatus.FAILED_SIZE_LIMIT] == 2
    assert stats.failures_today_by_status[EventStatus.FAILED_UNAVAILABLE] == 1


async def test_log_event_stores_title(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")
    await crud.log_event(
        db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS,
        video_id="abc123", title="My Cool Video", height=720, file_size_bytes=1000,
    )

    async with db.session() as session:
        from sqlalchemy import select as sa_select

        result = await session.execute(sa_select(Event).where(Event.video_id == "abc123"))
        event = result.scalar_one()
        assert event.title == "My Cool Video"


async def test_get_recent_downloads_returns_newest_first_and_only_success(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")

    await crud.log_event(
        db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS,
        video_id="first", title="First", height=480, file_size_bytes=1000,
    )
    await crud.log_event(
        db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.FAILED_ERROR,
        video_id="broken", title="Broken", height=720,
    )
    await crud.log_event(
        db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS,
        video_id="second", title="Second", height=720, file_size_bytes=2000,
    )

    entries = await crud.get_recent_downloads(db, 1)

    assert [e.video_id for e in entries] == ["second", "first"]
    assert entries[0].title == "Second"
    assert entries[0].height == 720
    assert entries[0].file_size_bytes == 2000


async def test_get_recent_downloads_respects_limit(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")
    for i in range(15):
        await crud.log_event(
            db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS,
            video_id=f"v{i}", title=f"Video {i}", height=720, file_size_bytes=1000,
        )

    entries = await crud.get_recent_downloads(db, 1, limit=5)
    assert len(entries) == 5


async def test_get_recent_downloads_only_for_requested_user(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")
    await crud.get_or_create_user(db, 2, "bob", "Bob")
    await crud.log_event(
        db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS,
        video_id="mine", title="Mine", height=720, file_size_bytes=1000,
    )
    await crud.log_event(
        db, user_id=2, stage=Stage.DOWNLOAD, status=EventStatus.SUCCESS,
        video_id="theirs", title="Theirs", height=720, file_size_bytes=1000,
    )

    entries = await crud.get_recent_downloads(db, 1)
    assert [e.video_id for e in entries] == ["mine"]


async def test_get_stats_counts_cancelled_and_excludes_from_failures(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")
    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.CANCELLED, height=720)
    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.FAILED_ERROR, height=480)

    stats = await crud.get_stats(db)

    assert stats.cancelled_today == 1
    assert EventStatus.CANCELLED not in stats.failures_today_by_status
    assert stats.failures_today_by_status[EventStatus.FAILED_ERROR] == 1


async def test_get_or_create_user_stores_language_code(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex", "en")

    async with db.session() as session:
        user = await session.get(User, 1)
        assert user.language_code == "en"


async def test_get_or_create_user_language_code_defaults_to_none(db):
    # Обратная совместимость: старые вызовы без language_code (и обновления
    # существующих пользователей клиентами, которые его не передают) не
    # должны падать — просто NULL.
    await crud.get_or_create_user(db, 1, "alex", "Alex")

    async with db.session() as session:
        user = await session.get(User, 1)
        assert user.language_code is None


async def test_get_or_create_user_updates_language_code_on_repeat_visit(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex", "en")
    await crud.get_or_create_user(db, 1, "alex", "Alex", "ru")

    async with db.session() as session:
        user = await session.get(User, 1)
        assert user.language_code == "ru"


async def test_get_stats_counts_non_ru_and_unknown_language_users(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex", "ru")
    await crud.get_or_create_user(db, 2, "bob", "Bob", "en")
    await crud.get_or_create_user(db, 3, "carl", "Carl", "uk")
    await crud.get_or_create_user(db, 4, "dave", "Dave", None)

    stats = await crud.get_stats(db)

    assert stats.total_users == 4
    assert stats.non_ru_users == 2  # en, uk
    assert stats.unknown_language_users == 1  # dave
