from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bot.db.models import Base

# (имя_таблицы, имя_колонки) -> DDL-тип для ALTER TABLE ... ADD COLUMN, если
# колонки не оказалось в уже существующей БД (см. Database._migrate). Только
# для колонок, добавленных ПОСЛЕ первого релиза — Base.metadata.create_all
# создаёт новые таблицы целиком с нуля, но не умеет добавлять новые колонки
# в уже существующие. Полноценной миграционной системы (Alembic) в проекте
# нет — для одной SQLite-таблицы это оверкилл, а вручную такие ALTER
# безопасны (это всегда NULLABLE-колонки).
_ADDED_COLUMNS: dict[tuple[str, str], str] = {
    ("events", "title"): "VARCHAR(300)",
}


def _sync_migrate(sync_conn) -> None:
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for (table_name, column_name), ddl_type in _ADDED_COLUMNS.items():
        if table_name not in existing_tables:
            # Таблицы вообще ещё нет — её создаст create_all с уже полной
            # схемой, добавлять колонку отдельно не нужно.
            continue
        columns = {col["name"] for col in inspector.get_columns(table_name)}
        if column_name in columns:
            continue
        sync_conn.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}")
        )


class Database:
    """Тонкая обёртка над async engine/sessionmaker SQLAlchemy.

    Создаётся один раз в bot/main.py и прокидывается в обработчики через
    aiogram DI (так же, как config и semaphore) — без глобального
    состояния модуля это проще тестировать: в тестах можно создать
    отдельный Database на sqlite+aiosqlite:///:memory:.
    """

    def __init__(self, database_url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(database_url)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            # Порядок важен: сначала миграция колонок в УЖЕ существующих
            # таблицах (на новой БД никаких таблиц ещё нет, миграция ничего
            # не сделает), потом create_all — создаёт с нуля то, чего нет
            # вообще, уже с полной, актуальной схемой.
            await conn.run_sync(_sync_migrate)
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session
