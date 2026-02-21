import time
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import RATE_LIMIT_MESSAGES, RATE_LIMIT_PERIOD

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self):
        self.user_messages: Dict[int, list] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        if not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id
        now = time.time()

        if user_id not in self.user_messages:
            self.user_messages[user_id] = []

        # Clean old timestamps
        self.user_messages[user_id] = [
            ts for ts in self.user_messages[user_id]
            if now - ts < RATE_LIMIT_PERIOD
        ]

        if len(self.user_messages[user_id]) >= RATE_LIMIT_MESSAGES:
            logger.warning(f"Rate limit hit for user {user_id}")
            await event.answer(
                "⏳ Слишком много сообщений. Подождите минуту."
            )
            return

        self.user_messages[user_id].append(now)

        # Cleanup inactive users
        if len(self.user_messages) > 1000:
            self.user_messages = {
                uid: timestamps
                for uid, timestamps in self.user_messages.items()
                if timestamps and now - timestamps[-1] < RATE_LIMIT_PERIOD * 5
            }

        return await handler(event, data)
