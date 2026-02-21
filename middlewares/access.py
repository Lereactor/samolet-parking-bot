import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from config import ADMIN_ID, STAFF_IDS

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    def __init__(self, db):
        self.db = db

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        data["db"] = self.db

        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id
            data["is_admin"] = user_id == ADMIN_ID
            data["is_moderator"] = user_id in STAFF_IDS

            user = await self.db.get_user(user_id)
            if user:
                data["user_status"] = user["status"]
                data["is_approved"] = user["status"] == "approved"
            else:
                data["user_status"] = "new"
                data["is_approved"] = False
        else:
            data["is_admin"] = False
            data["is_moderator"] = False
            data["user_status"] = "new"
            data["is_approved"] = False

        return await handler(event, data)
