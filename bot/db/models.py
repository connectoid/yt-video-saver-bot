from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Stage:
    """Этап воронки, к которому относится событие."""

    INFO_FETCH = "info_fetch"
    DOWNLOAD = "download"


class EventStatus:
    """Результат события — по этим значениям строится аналитика "на чём
    отваливаются пользователи" (см. bot/db/crud.py::get_stats)."""

    SUCCESS = "success"
    FAILED_UNAVAILABLE = "failed_unavailable"
    FAILED_LIVE = "failed_live"
    FAILED_NO_FORMATS = "failed_no_formats"
    FAILED_SIZE_LIMIT = "failed_size_limit"
    FAILED_ERROR = "failed_error"
    BLOCKED_DAILY_LIMIT = "blocked_daily_limit"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user_id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    events: Mapped[list["Event"]] = relationship(back_populates="user")


class Event(Base):
    """Одно событие воронки: попытка получить метаданные видео или
    скачать конкретное разрешение, с итоговым статусом.

    Хранится по одной строке на попытку (а не только на успех), чтобы
    можно было считать не только "сколько скачали", но и "на чём
    отваливаются" — см. Stage/EventStatus выше.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    stage: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32))
    video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(back_populates="events")
