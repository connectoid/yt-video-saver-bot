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
    ("users", "language_code"): "VARCHAR(8)",
}

# (имя_индекса) -> (таблица, колонки по порядку) для CREATE INDEX на уже
# существующей таблице — тот же смысл, что и у _ADDED_COLUMNS, только для
# индексов, добавленных после первого релиза (см. Index в
# Event.__table_args__, bot/db/models.py). SQLite понимает
# "CREATE INDEX IF NOT EXISTS" нативно, поэтому, в отличие от колонок,
# отдельная проверка "уже есть или нет" через inspector не нужна — запрос
# идемпотентен сам по себе.
_ADDED_INDEXES: dict[str, tuple[str, tuple[str, ...]]] = {
    "ix_events_user_id_created_at": ("events", ("user_id", "created_at")),
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

    # Индексы — после колонок: если бы индексу когда-нибудь понадобилась
    # колонка из _ADDED_COLUMNS выше, она должна успеть появиться раньше.
    for index_name, (table_name, columns) in _ADDED_INDEXES.items():
        if table_name not in existing_tables:
            continue
        columns_sql = ", ".join(columns)
        sync_conn.execute(
            text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns_sql})")
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
