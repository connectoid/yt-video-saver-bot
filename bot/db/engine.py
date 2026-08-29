from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bot.db.models import Base


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
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session
