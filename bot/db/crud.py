from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select

from bot.db.engine import Database
from bot.db.models import BlockedVideo, Event, EventStatus, Stage, User


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
    language_code: str | None = None,
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
                    language_code=language_code,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            user.username = username
            user.full_name = full_name
            # Обновляем и для уже существующих пользователей (не только при
            # создании) — так же, как username/full_name: если человек сменит
            # язык интерфейса Telegram, /stats это со временем подхватит, а не
            # застрянет на значении с самого первого сообщения. Апдейт NULL'ом
            # безопасен только если Telegram реально прислал None — apps почти
            # всегда шлют язык, так что практического риска "затереть
            # известное значение неизвестным" почти нет.
            user.language_code = language_code
            user.last_seen_at = now
        await session.commit()


async def log_event(
    db: Database,
    *,
    user_id: int,
    stage: str,
    status: str,
    video_id: str | None = None,
    title: str | None = None,
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
                title=title,
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
class DownloadHistoryEntry:
    title: str | None
    video_id: str | None
    height: int | None
    file_size_bytes: int | None
    created_at: dt.datetime


async def get_recent_downloads(
    db: Database, user_id: int, limit: int = 10
) -> list[DownloadHistoryEntry]:
    """Последние УСПЕШНЫЕ скачивания пользователя, новые сначала — для
    команды /history. Неудачные попытки и отменённые скачивания сюда
    намеренно не попадают, это история того, что реально было скачано."""
    async with db.session() as session:
        result = await session.execute(
            select(Event)
            .where(
                Event.user_id == user_id,
                Event.stage == Stage.DOWNLOAD,
                Event.status == EventStatus.SUCCESS,
            )
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
        return [
            DownloadHistoryEntry(
                title=event.title,
                video_id=event.video_id,
                height=event.height,
                file_size_bytes=event.file_size_bytes,
                created_at=event.created_at,
            )
            for event in result.scalars().all()
        ]


async def is_video_blocked(db: Database, video_id: str) -> bool:
    """Проверка блок-листа — вызывается ДО похода в yt-dlp (см.
    bot/handlers/video.py::handle_link), поэтому должна быть дешёвой:
    один select по первичному ключу."""
    async with db.session() as session:
        return await session.get(BlockedVideo, video_id) is not None


async def block_video(db: Database, video_id: str, reason: str | None = None) -> None:
    """Добавить video_id в блок-лист (или обновить причину, если он там
    уже есть) — используется командой /block."""
    async with db.session() as session:
        existing = await session.get(BlockedVideo, video_id)
        if existing is not None:
            existing.reason = reason
        else:
            session.add(BlockedVideo(video_id=video_id, reason=reason))
        await session.commit()


async def unblock_video(db: Database, video_id: str) -> bool:
    """Убрать video_id из блок-листа — используется командой /unblock.
    Возвращает True, если запись действительно была и её удалили."""
    async with db.session() as session:
        existing = await session.get(BlockedVideo, video_id)
        if existing is None:
            return False
        await session.delete(existing)
        await session.commit()
        return True


async def list_blocked_videos(db: Database) -> list[BlockedVideo]:
    """Все заблокированные video_id, новые сначала — для команды
    /blocklist."""
    async with db.session() as session:
        result = await session.execute(
            select(BlockedVideo).order_by(BlockedVideo.blocked_at.desc())
        )
        return list(result.scalars().all())


@dataclass
class Stats:
    total_users: int
    new_users_today: int
    active_users_today: int
    downloads_success_today: int
    downloads_success_total: int
    blocked_by_limit_today: int
    blocked_video_today: int
    cancelled_today: int
    feedback_today: int
    # Данные для решения "нужна ли RU/EN-локализация" (User.language_code —
    # язык клиента Telegram, не выбор языка в боте). non_ru_users и
    # unknown_language_users вместе с total_users дают разбивку: известно-RU,
    # известно-не-RU, неизвестно (ещё не писал после появления колонки, или
    # Telegram не прислал значение).
    non_ru_users: int
    unknown_language_users: int
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

        cancelled_today = (
            await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.status == EventStatus.CANCELLED,
                    Event.created_at >= start,
                )
            )
        ).scalar_one()

        blocked_video_today = (
            await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.status == EventStatus.BLOCKED_VIDEO,
                    Event.created_at >= start,
                )
            )
        ).scalar_one()

        feedback_today = (
            await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.stage == Stage.FEEDBACK,
                    Event.status == EventStatus.SUCCESS,
                    Event.created_at >= start,
                )
            )
        ).scalar_one()

        # За ВСЁ время (не только сегодня) — это медленно меняющийся срез
        # аудитории в целом, не однодневное событие вроде остальных полей
        # выше.
        non_ru_users = (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.language_code.is_not(None), User.language_code != "ru")
            )
        ).scalar_one()

        unknown_language_users = (
            await session.execute(
                select(func.count()).select_from(User).where(User.language_code.is_(None))
            )
        ).scalar_one()

        failure_rows = await session.execute(
            select(Event.status, func.count())
            .where(
                Event.status.notin_(
                    [
                        EventStatus.SUCCESS,
                        EventStatus.BLOCKED_DAILY_LIMIT,
                        EventStatus.BLOCKED_VIDEO,
                        EventStatus.CANCELLED,
                    ]
                ),
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
            blocked_video_today=blocked_video_today,
            cancelled_today=cancelled_today,
            feedback_today=feedback_today,
            non_ru_users=non_ru_users,
            unknown_language_users=unknown_language_users,
            failures_today_by_status=failures_today_by_status,
        )
