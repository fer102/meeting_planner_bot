from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from database.db import Database
from keyboards.reply import main_menu_keyboard
from keyboards.inline import timezone_keyboard, meeting_options_keyboard
from utils.time_helpers import get_timezone_display, utc_to_local
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, db: Database, state: FSMContext = None, **kwargs):
    if state:
        await state.clear()
    
    if command and command.args:
        if command.args.startswith("meeting_"):
            try:
                meeting_id = int(command.args.replace("meeting_", ""))
                logger.info(f"Пользователь {message.from_user.id} перешел по ссылке на встречу {meeting_id}")
                
                meeting = await db.get_meeting(meeting_id)
                if not meeting:
                    await message.answer("❌ Встреча не найдена или была удалена.")
                    return
                
                user = await db.get_user(message.from_user.id)
                
                if not user:
                    logger.info(f"Новый пользователь {message.from_user.id} перешел по ссылке, требуется регистрация")
                    if state:
                        await state.update_data(pending_meeting_id=meeting_id)
                    
                    await message.answer(
                        "👋 Для участия в голосовании сначала выберите ваш часовой пояс:",
                        reply_markup=timezone_keyboard()
                    )
                    return
                
                await show_meeting_for_voting(message, meeting_id, user, db)
                
            except ValueError as e:
                logger.error(f"Ошибка при парсинге meeting_id: {e}")
                await message.answer("❌ Неверная ссылка-приглашение.")
            except Exception as e:
                logger.error(f"Ошибка при обработке ссылки на встречу: {e}", exc_info=True)
                await message.answer("❌ Произошла ошибка при загрузке встречи.")
            return
    
    need_registration = kwargs.get('need_registration', False)
    
    if need_registration:
        await message.answer(
            "👋 Добро пожаловать в бот для планирования встреч!\n\n"
            "Для начала работы выберите ваш часовой пояс:",
            reply_markup=timezone_keyboard()
        )
        return
    
    user = kwargs.get('user')
    if not user:
        user = await db.get_user(message.from_user.id)
    
    if user:
        timezone_display = get_timezone_display(user['timezone'])
        
        await message.answer(
            f"С возвращением! 👋\n"
            f"Ваш часовой пояс: {timezone_display}\n\n"
            "Выберите действие:",
            reply_markup=main_menu_keyboard()
        )
    else:
        await message.answer(
            "👋 Добро пожаловать в бот для планирования встреч!\n\n"
            "Для начала работы выберите ваш часовой пояс:",
            reply_markup=timezone_keyboard()
        )

@router.message(F.text == "🚀 Старт")
async def start_button_handler(message: Message, db: Database, state: FSMContext):
    await cmd_start(message, None, db, state)

@router.callback_query(F.data.startswith("tz_"))
async def process_timezone_choice(callback: CallbackQuery, db: Database, state: FSMContext):
    utc_offset = callback.data.replace("tz_", "")
    
    user = await db.get_user(callback.from_user.id)
    
    if not user:
        await db.create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            timezone=utc_offset
        )
        await callback.message.edit_text(
            f"✅ Регистрация завершена!\n"
            f"Ваш часовой пояс установлен: {get_timezone_display(utc_offset)}"
        )
        logger.info(f"Новый пользователь зарегистрирован: {callback.from_user.id}, пояс: {utc_offset}")
        
        user = await db.get_user(callback.from_user.id)
        
        state_data = await state.get_data()
        pending_meeting_id = state_data.get('pending_meeting_id')
        
        if pending_meeting_id:
            logger.info(f"Пользователь {callback.from_user.id} переходит к голосованию за встречу {pending_meeting_id}")
            await state.update_data(pending_meeting_id=None)
            await show_meeting_for_voting(callback.message, pending_meeting_id, user, db)
        else:
            await callback.message.answer(
                "Выберите действие:",
                reply_markup=main_menu_keyboard()
            )
    else:
        await db.update_user_timezone(callback.from_user.id, utc_offset)
        await callback.message.edit_text(
            f"✅ Часовой пояс обновлен!\n"
            f"Теперь ваш часовой пояс: {get_timezone_display(utc_offset)}"
        )
        logger.info(f"Пользователь {callback.from_user.id} обновил часовой пояс на {utc_offset}")
        
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=main_menu_keyboard()
        )
    
    await state.clear()
    await callback.answer()

async def show_meeting_for_voting(message: Message, meeting_id: int, user, db: Database):
    try:
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await message.answer("❌ Встреча не найдена или была удалена.")
            return
        
        await db.add_participant(meeting_id, user['id'])
        logger.info(f"Пользователь {user['id']} добавлен в участники встречи {meeting_id}")
        
        options = await db.get_meeting_options(meeting_id)
        
        if not options:
            await message.answer("❌ У этой встречи нет вариантов времени для голосования.")
            return
        
        user_votes = await db.get_user_votes(meeting_id, user['id'])
        
        for opt in options:
            opt['display_time'] = utc_to_local(opt['option_datetime'], user['timezone'])
        
        await message.answer(
            f"📅 Встреча: {meeting['title']}\n\n"
            f"Описание: {meeting['description'] or 'Нет описания'}\n\n"
            f"Выберите удобные для вас варианты времени:",
            reply_markup=meeting_options_keyboard(meeting_id, options, user_votes)
        )
        
        logger.info(f"Пользователю {user['id']} показаны варианты для встречи {meeting_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при показе встречи для голосования: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при загрузке встречи.")

@router.callback_query(F.data == "back")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=None
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()