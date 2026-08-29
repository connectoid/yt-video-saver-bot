from __future__ import annotations


def should_emit_progress(
    *,
    last_sent_at: float | None,
    last_fraction: float | None,
    last_label: str | None,
    now: float,
    fraction: float | None,
    label: str,
    min_interval: float = 3.0,
    min_delta: float = 0.05,
) -> bool:
    """Решает, стоит ли сейчас отправлять апдейт прогресса в Telegram.

    Прогресс-хук yt-dlp может дёргаться десятки раз в секунду — без троттлинга
    это быстро упрётся в лимиты Telegram на редактирование сообщений (и просто
    не нужно пользователю). Правила:
    - первый апдейт всегда отправляется;
    - смена стадии (видео -> аудио -> обработка) отправляется сразу, не дожидаясь
      min_interval — пользователю важно увидеть, что процесс не завис, а перешёл
      дальше;
    - достижение 100% отправляется сразу;
    - иначе — не чаще раза в min_interval секунд, и только если процент успел
      заметно (>= min_delta) измениться с прошлого отправленного апдейта.
    """
    if last_sent_at is None:
        return True
    if label != last_label:
        return True
    if fraction is not None and fraction >= 1.0:
        return True
    if now - last_sent_at < min_interval:
        return False
    if fraction is not None and last_fraction is not None:
        return abs(fraction - last_fraction) >= min_delta
    return True
