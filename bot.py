import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from database.db import Database
from middlewares.registration import RegistrationMiddleware

# Настраиваем логирование ДО всего остального
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Вывод в консоль
        logging.FileHandler('bot.log')  # Сохранение в файл
    ]
)

logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в .env файле!")
    exit(1)

logger.info("Инициализация бота...")
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Импортируем все роутеры
from handlers import start, menu, create_meeting, voting, my_meetings, reminders

dp.include_router(start.router)
dp.include_router(menu.router)
dp.include_router(create_meeting.router)
dp.include_router(voting.router)
dp.include_router(my_meetings.router)
dp.include_router(reminders.router)

async def main():
    logger.info("Запуск бота...")
    
    db = Database()
    await db.create_tables()
    logger.info("База данных инициализирована")
    
    dp.update.middleware(RegistrationMiddleware())
    dp.workflow_data.update({'db': db})
    
    # Запускаем задачу напоминаний
    from handlers.reminders import setup_reminder_task
    setup_reminder_task(dp, bot, db)
    
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"Бот @{bot_info.username} (ID: {bot_info.id}) запущен и готов к работе")
    
    # Удаляем вебхук перед запуском polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("Начинаем polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)