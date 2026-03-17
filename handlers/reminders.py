from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from database.db import Database
import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
router = Router()

async def check_reminders(bot, db: Database):
    """Фоновая задача для проверки и отправки напоминаний"""
    logger.info("Задача напоминаний запущена")
    while True:
        try:
            reminders = await db.get_reminders_to_send()
            now = datetime.now(timezone.utc)
            
            for reminder in reminders:
                try:
                    meeting_time = datetime.fromisoformat(reminder['option_datetime'].replace('Z', '+00:00'))
                    reminder_time = meeting_time - timedelta(minutes=reminder['reminder_minutes'])
                    
                    # Отправляем напоминание за указанное время (с погрешностью 1 минута)
                    time_diff = (reminder_time - now).total_seconds()
                    
                    if abs(time_diff) < 60:  # Если разница меньше минуты
                        user = await db.get_user_by_id(reminder['user_id'])
                        if user:
                            await bot.send_message(
                                user['telegram_id'],
                                f"⏰ Напоминание о встрече \"{reminder['title']}\"\n\n"
                                f"Встреча состоится через {reminder['reminder_minutes']} минут!"
                            )
                            
                            await db.mark_reminder_sent(reminder['reminder_id'])
                            logger.info(f"Напоминание отправлено пользователю {user['telegram_id']}")
                except Exception as e:
                    logger.error(f"Ошибка обработки напоминания {reminder.get('reminder_id')}: {e}")
            
            # Проверяем каждые 30 секунд
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче напоминаний: {e}", exc_info=True)
            await asyncio.sleep(60)

def setup_reminder_task(dp, bot, db):
    """Запускает фоновую задачу напоминаний"""
    loop = asyncio.get_event_loop()
    task = loop.create_task(check_reminders(bot, db))
    logger.info("Фоновая задача напоминаний запущена")
    return task