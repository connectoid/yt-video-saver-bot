from aiogram import Router

from .common import router as common_router
from .video import router as video_router


def get_root_router() -> Router:
    root = Router(name="root")
    root.include_router(common_router)
    root.include_router(video_router)
    return root
