import pytest

from bot.db import crud
from bot.db.engine import Database
from bot.db.models import EventStatus, Stage


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await database.create_all()
    yield database
    await database.close()


async def test_is_video_blocked_false_by_default(db):
    assert await crud.is_video_blocked(db, "abc12345678") is False


async def test_block_then_is_blocked(db):
    await crud.block_video(db, "dQw4w9WgXcQ", reason="жалоба правообладателя")
    assert await crud.is_video_blocked(db, "dQw4w9WgXcQ") is True


async def test_block_is_idempotent_and_updates_reason(db):
    await crud.block_video(db, "dQw4w9WgXcQ", reason="first reason")
    await crud.block_video(db, "dQw4w9WgXcQ", reason="updated reason")

    entries = await crud.list_blocked_videos(db)
    assert len(entries) == 1
    assert entries[0].reason == "updated reason"


async def test_unblock_removes_entry(db):
    await crud.block_video(db, "dQw4w9WgXcQ")
    removed = await crud.unblock_video(db, "dQw4w9WgXcQ")

    assert removed is True
    assert await crud.is_video_blocked(db, "dQw4w9WgXcQ") is False


async def test_unblock_missing_entry_returns_false(db):
    removed = await crud.unblock_video(db, "doesNotExist")
    assert removed is False


async def test_list_blocked_videos_newest_first(db):
    await crud.block_video(db, "first_video")
    await crud.block_video(db, "second_video")

    entries = await crud.list_blocked_videos(db)
    assert [e.video_id for e in entries] == ["second_video", "first_video"]


async def test_get_stats_counts_blocked_video_today(db):
    await crud.get_or_create_user(db, 1, "alex", "Alex")
    await crud.log_event(
        db, user_id=1, stage=Stage.INFO_FETCH, status=EventStatus.BLOCKED_VIDEO,
        video_id="dQw4w9WgXcQ",
    )
    await crud.log_event(db, user_id=1, stage=Stage.DOWNLOAD, status=EventStatus.FAILED_ERROR, height=480)

    stats = await crud.get_stats(db)

    assert stats.blocked_video_today == 1
    # BLOCKED_VIDEO не должен попадать в "провалы по причинам" — это не
    # ошибка/сбой, а осознанный отказ, как и BLOCKED_DAILY_LIMIT/CANCELLED.
    assert EventStatus.BLOCKED_VIDEO not in stats.failures_today_by_status
    assert stats.failures_today_by_status[EventStatus.FAILED_ERROR] == 1
