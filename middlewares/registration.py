from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from database.db import Database
import logging

logger = logging.getLogger(__name__)

class RegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        db: Database = data.get('db')
        
        if not db:
            return await handler(event, data)
        
        if isinstance(event, Message):
            user_id = event.from_user.id
            username = event.from_user.username
            if event.text and event.text.startswith('/start'):
                user = await db.get_user(user_id)
                data['user'] = user
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            username = event.from_user.username
        else:
            return await handler(event, data)

        user = await db.get_user(user_id)
        
        if not user:
            data['need_registration'] = True
            data['temp_user'] = {'telegram_id': user_id, 'username': username}
            logger.info(f"Новый пользователь {user_id}, требуется регистрация")
        else:
            data['user'] = user
        
        return await handler(event, data)