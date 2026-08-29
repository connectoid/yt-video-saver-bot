from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select

from bot.db.engine import Database
from bot.db.models import Event, EventStatus, Stage, User


def today_utc_start(now: dt.datetime | None = None) -> dt.datetime:
    """Начало текущих UTC-суток — граница, относительно которой считается
    дневной лимит и вся посуточная аналитика. Вынесено в отдельную функцию
    с необязательным `now`, чтобы было легко тестировать без реального
    времени."""
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_or_create_user(
    db: Database,
    user_id: int,
    username: str | None,
    full_name: str | None,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    async with db.session() as session:
        user = await session.get(User, user_id)
        if user is None:
            session.add(
                User(
                    id=user_id,
                    username=username,
                    full_name=full_name,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            user.username = username
            user.full_name = full_name
            user.last_seen_at = now
        await session.commit()


async def log_event(
    db: Database,
    *,
    user_id: int,
    stage: str,
    status: str,
    video_id: str | None = None,
    height: int | None = None,
    file_size_bytes: int | None = None,
) -> None:
    async with db.session() as session:
        session.add(
            Event(
                user_id=user_id,
                stage=stage,
                status=status,
                video_id=video_id,
                height=height,
                file_size_bytes=file_size_bytes,
            )
        )
        await session.commit()


async def count_successful_downloads_today(
    db: Database, user_id: int, now: dt.datetime | None = None
) -> int:
    start = today_utc_start(now)
    async with db.session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Event)
            .where(
                Event.user_id == user_id,
                Event.stage == Stage.DOWNLOAD,
                Event.status == EventStatus.SUCCESS,
                Event.created_at >= start,
            )
        )
        return result.scalar_one()


@dataclass
class Stats:
    total_users: int
    new_users_today: int
    active_users_today: int
    downloads_success_today: int
    downloads_success_total: int
    blocked_by_limit_today: int
    failures_today_by_status: dict[str, int]


async def get_stats(db: Database, now: dt.datetime | None = None) -> Stats:
    start = today_utc_start(now)
    async with db.session() as session:
        total_users = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()

        new_users_today = (
            await session.execute(
                select(func.count()).select_from(User).where(User.first_seen_at >= start)
            )
        ).scalar_one()

        active_users_today = (
            await session.execute(
                select(func.count(func.distinct(Event.user_id))).where(
                    Event.created_at >= start
                )
            )
        ).scalar_one()

        downloads_success_today = (
            await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.stage == Stage.DOWNLOAD,
                    Event.status == EventStatus.SUCCESS,
                    Event.created_at >= start,
                )
            )
        ).scalar_one()

        downloads_success_total = (
            await session.execute(
                select(func.count())
                .select_from(Event)
                .where(Event.stage == Stage.DOWNLOAD, Event.status == EventStatus.SUCCESS)
            )
        ).scalar_one()

        blocked_by_limit_today = (
            await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.status == EventStatus.BLOCKED_DAILY_LIMIT,
                    Event.created_at >= start,
                )
            )
        ).scalar_one()

        failure_rows = await session.execute(
            select(Event.status, func.count())
            .where(
                Event.status.notin_([EventStatus.SUCCESS, EventStatus.BLOCKED_DAILY_LIMIT]),
                Event.created_at >= start,
            )
            .group_by(Event.status)
        )
        failures_today_by_status = dict(failure_rows.all())

        return Stats(
            total_users=total_users,
            new_users_today=new_users_today,
            active_users_today=active_users_today,
            downloads_success_today=downloads_success_today,
            downloads_success_total=downloads_success_total,
            blocked_by_limit_today=blocked_by_limit_today,
            failures_today_by_status=failures_today_by_status,
        )
