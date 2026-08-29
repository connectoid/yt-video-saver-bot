"""Проверка Database.create_all() как мини-миграции для уже существующих БД.

На проде events уже была создана ДО того, как в ней появилась колонка
title (см. bot/db/engine.py::_sync_migrate) — Base.metadata.create_all сам
по себе такую колонку в существующую таблицу не добавит, нужен явный
ALTER TABLE. Здесь эмулируем "старую" БД (создаём events по старой схеме
руками, без title) и проверяем, что после create_all() колонка появляется,
а старые строки остаются читаемыми (title у них — NULL, не ошибка).
"""

import sqlalchemy as sa

from bot.db.engine import Database
from bot.db.models import Event


async def test_create_all_adds_title_column_to_existing_table(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/legacy.db")

    # "Старая" схема — events без колонки title, как было бы на проде до
    # деплоя этого изменения.
    async with database.engine.begin() as conn:
        await conn.execute(
            sa.text(
                "CREATE TABLE events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id BIGINT NOT NULL, "
                "created_at DATETIME, "
                "stage VARCHAR(16), "
                "status VARCHAR(32), "
                "video_id VARCHAR(32), "
                "height INTEGER, "
                "file_size_bytes INTEGER"
                ")"
            )
        )
        await conn.execute(
            sa.text(
                "INSERT INTO events (user_id, stage, status, video_id, height) "
                "VALUES (1, 'download', 'success', 'legacyid', 720)"
            )
        )

    await database.create_all()

    async with database.session() as session:
        result = await session.execute(sa.select(Event).where(Event.video_id == "legacyid"))
        event = result.scalar_one()
        assert event.title is None  # старая строка — колонки ещё не было
        assert event.height == 720

    await database.close()


async def test_create_all_is_idempotent_on_fresh_db(tmp_path):
    # На чистой БД (create_all с нуля, миграция ничего не находит — и не
    # должна падать на "таблицы ещё нет") title должен просто нормально
    # писаться и читаться.
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/fresh.db")
    await database.create_all()
    await database.create_all()  # повторный вызов не должен падать

    async with database.session() as session:
        session.add(
            Event(user_id=1, stage="download", status="success", video_id="x", title="Title")
        )
        await session.commit()

        result = await session.execute(sa.select(Event).where(Event.video_id == "x"))
        event = result.scalar_one()
        assert event.title == "Title"

    await database.close()
