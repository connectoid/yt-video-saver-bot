from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field


@dataclass
class PendingDownload:
    url: str
    title: str
    formats: dict[int, str]  # height -> yt-dlp format selector
    created_at: float = field(default_factory=time.monotonic)


class RequestCache:
    """Короткоживущее in-memory хранилище: короткий request_id -> URL видео
    и доступные форматы, показанные на инлайн-клавиатуре.

    callback_data в Telegram ограничен 64 байтами, поэтому нельзя засунуть
    туда полный URL YouTube и строку формата. Вместо этого выдаём короткий
    случайный id и храним настоящие данные здесь до использования/истечения.
    """

    def __init__(self, ttl_seconds: int = 900) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, PendingDownload] = {}

    def put(self, pending: PendingDownload) -> str:
        self._sweep()
        request_id = secrets.token_hex(4)
        while request_id in self._store:
            request_id = secrets.token_hex(4)
        self._store[request_id] = pending
        return request_id

    def get(self, request_id: str) -> PendingDownload | None:
        pending = self._store.get(request_id)
        if pending is None:
            return None
        if time.monotonic() - pending.created_at > self._ttl:
            self._store.pop(request_id, None)
            return None
        return pending

    def _sweep(self) -> None:
        now = time.monotonic()
        expired = [
            rid for rid, p in self._store.items() if now - p.created_at > self._ttl
        ]
        for rid in expired:
            self._store.pop(rid, None)
