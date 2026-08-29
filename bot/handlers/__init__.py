from aiogram import Router

from .account import router as account_router
from .admin import router as admin_router
from .common import router as common_router
from .feedback import router as feedback_router
from .video import router as video_router


def get_root_router() -> Router:
    root = Router(name="root")
    root.include_router(common_router)
    # admin/account/feedback — до video, иначе их команды перехватит
    # catch-all F.text в video (у него там ловится вообще любой текст)
    root.include_router(admin_router)
    root.include_router(account_router)
    root.include_router(feedback_router)
    root.include_router(video_router)
    return root
