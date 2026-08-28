from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Библиотеки бывают многословны на DEBUG/INFO — приглушаем шум.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
