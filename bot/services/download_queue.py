from __future__ import annotations

import asyncio


def queue_ahead_count(position: int, max_concurrent: int) -> int:
    """Сколько скачиваний реально стоят перед данным, пока оно ждёт слот.

    position — 0-based место в общем списке ожидающих/качающих (см.
    DownloadQueue.position). Первые max_concurrent мест уже помещаются в
    семафор и начинают качаться сразу, так что для них "перед вами: 0" —
    ждать не нужно.
    """
    return max(0, position - max_concurrent + 1)


class DownloadQueue:
    """Учёт очереди на скачивание — только для UI (показать пользователю
    примерную позицию), реальное ограничение конкурентности по-прежнему
    делает asyncio.Semaphore в handlers/video.py.

    MVP: состояние в памяти процесса. При масштабировании на несколько
    инстансов бота (как и request_cache) это нужно будет вынести в
    Redis/БД — см. README, roadmap.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._order: list[int] = []
        self._next_token = 0

    async def enter(self) -> int:
        """Встать в очередь, вернуть токен для последующих position()/leave()."""
        async with self._lock:
            token = self._next_token
            self._next_token += 1
            self._order.append(token)
            return token

    async def position(self, token: int) -> int:
        """0-based место в очереди на момент вызова."""
        async with self._lock:
            try:
                return self._order.index(token)
            except ValueError:
                return 0

    async def leave(self, token: int) -> None:
        """Покинуть очередь (скачивание завершилось — успешно или нет)."""
        async with self._lock:
            if token in self._order:
                self._order.remove(token)
