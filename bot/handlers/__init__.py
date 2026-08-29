from aiogram import Router

from .admin import router as admin_router
from .common import router as common_router
from .video import router as video_router


def get_root_router() -> Router:
    root = Router(name="root")
    root.include_router(common_router)
    # admin — до video, иначе "/stats" перехватит catch-all F.text в video
    root.include_router(admin_router)
    root.include_router(video_router)
    return root
