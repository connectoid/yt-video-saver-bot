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
