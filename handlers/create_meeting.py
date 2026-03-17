from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database.db import Database
from keyboards.reply import main_menu_keyboard, cancel_keyboard
from keyboards.inline import date_selection_keyboard, time_selection_keyboard
from states.meeting_states import CreateMeeting
from utils.time_helpers import get_available_dates, local_to_utc
import logging

logger = logging.getLogger(__name__)
router = Router()

temp_meeting_data = {}

@router.message(Command("create"))
async def create_meeting_command(message: Message, db: Database, state: FSMContext):
    await start_creating_meeting(message, db, state)

@router.message(F.text == "📅 Создать встречу")
async def create_meeting_button(message: Message, db: Database, state: FSMContext):
    await start_creating_meeting(message, db, state)

async def start_creating_meeting(message: Message, db: Database, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer(
            "❌ Сначала нужно зарегистрироваться!\n"
            "Нажмите /start для регистрации."
        )
        return
    
    logger.info(f"Пользователь {message.from_user.id} начинает создание встречи")
    await state.set_state(CreateMeeting.title)
    await message.answer(
        "📝 Введите название встречи:",
        reply_markup=cancel_keyboard()
    )

@router.message(CreateMeeting.title, F.text)
async def process_meeting_title(message: Message, state: FSMContext, db: Database):
    logger.info(f"Пользователь {message.from_user.id} ввел название: {message.text}")
    
    if message.text == "❌ Отмена":
        logger.info(f"Пользователь {message.from_user.id} отменил создание встречи")
        await state.clear()
        await message.answer(
            "Создание встречи отменено.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if len(message.text) > 100:
        await message.answer(
            "❌ Название слишком длинное. Используйте не более 100 символов.\n"
            "Введите название встречи:"
        )
        return
    
    await state.update_data(title=message.text)
    await state.set_state(CreateMeeting.description)
    
    await message.answer(
        "📄 Введите описание встречи (можно отправить пустое сообщение):",
        reply_markup=cancel_keyboard()
    )

@router.message(CreateMeeting.description)
async def process_meeting_description(message: Message, state: FSMContext, db: Database):
    logger.info(f"Пользователь {message.from_user.id} ввел описание: {message.text if message.text else 'пусто'}")
    
    if message.text == "❌ Отмена":
        logger.info(f"Пользователь {message.from_user.id} отменил создание встречи")
        await state.clear()
        await message.answer(
            "Создание встречи отменено.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    description = message.text if message.text else ""
    await state.update_data(description=description)
    
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    temp_meeting_data[user_id] = {
        'selected_dates': [],
        'selected_times': {},
        'current_date_idx': 0
    }
    logger.info(f"Инициализированы временные данные для пользователя {user_id}")
    
    await state.set_state(CreateMeeting.choosing_dates)
    
    # Передаем часовой пояс пользователя для фильтрации сегодняшней даты
    await message.answer(
        "📅 Выберите даты для встречи (можно выбрать несколько):\n"
        "Нажимайте на даты, чтобы выбрать/отменить выбор.\n"
        "Когда закончите, нажмите '✅ Готово'.",
        reply_markup=date_selection_keyboard(user_timezone=user['timezone'])
    )

@router.callback_query(CreateMeeting.choosing_dates, F.data.startswith("date_"))
async def select_date_callback(callback: CallbackQuery, state: FSMContext, db: Database):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал дату с callback_data: {callback.data}")
    
    if user_id not in temp_meeting_data:
        await callback.answer("Ошибка! Начните создание встречи заново.")
        await state.clear()
        return
    
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("Ошибка! Пользователь не найден.")
        return
    
    try:
        date_idx = int(callback.data.replace("date_", ""))
        logger.info(f"Индекс выбранной даты: {date_idx}")
    except ValueError:
        await callback.answer("Ошибка обработки данных")
        return
    
    available_dates = get_available_dates(user['timezone'])
    if date_idx >= len(available_dates):
        await callback.answer("Ошибка: дата не найдена")
        return
    
    date_str = available_dates[date_idx].strftime("%d.%m.%Y")
    logger.info(f"Выбрана дата: {date_str}")
    
    if date_str in temp_meeting_data[user_id]['selected_dates']:
        temp_meeting_data[user_id]['selected_dates'].remove(date_str)
        logger.info(f"Дата {date_str} удалена из выбранных")
    else:
        temp_meeting_data[user_id]['selected_dates'].append(date_str)
        logger.info(f"Дата {date_str} добавлена в выбранные")
    
    logger.info(f"Текущие выбранные даты: {temp_meeting_data[user_id]['selected_dates']}")
    
    await callback.message.edit_text(
        "📅 Выберите даты для встречи (можно выбрать несколько):\n"
        "Нажимайте на даты, чтобы выбрать/отменить выбор.\n"
        "Когда закончите, нажмите '✅ Готово'.",
        reply_markup=date_selection_keyboard(temp_meeting_data[user_id]['selected_dates'], user['timezone'])
    )
    
    await callback.answer()

@router.callback_query(CreateMeeting.choosing_dates, F.data == "dates_done")
async def dates_done_callback(callback: CallbackQuery, state: FSMContext, db: Database):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} завершил выбор дат")
    
    if user_id not in temp_meeting_data:
        await callback.answer("Ошибка! Начните создание встречи заново.")
        await state.clear()
        return
    
    selected_dates = temp_meeting_data[user_id]['selected_dates']
    logger.info(f"Выбранные даты: {selected_dates}")
    
    if not selected_dates:
        await callback.answer("❌ Выберите хотя бы одну дату!")
        return
    
    # Получаем пользователя для его часового пояса
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("Ошибка! Пользователь не найден.")
        return
    
    temp_meeting_data[user_id]['current_date_idx'] = 0
    current_date = selected_dates[0]
    logger.info(f"Переход к выбору времени для даты: {current_date}")
    
    available_dates = get_available_dates()
    date_idx = None
    for i, d in enumerate(available_dates):
        if d.strftime("%d.%m.%Y") == current_date:
            date_idx = i
            break
    
    if date_idx is None:
        await callback.answer("Ошибка с датой!")
        return
    
    logger.info(f"Индекс даты {current_date}: {date_idx}")
    
    await state.set_state(CreateMeeting.choosing_time)
    
    selected_times = temp_meeting_data[user_id]['selected_times'].get(current_date, [])
    logger.info(f"Ранее выбранное время для {current_date}: {selected_times}")
    
    # Передаем часовой пояс пользователя в клавиатуру
    await callback.message.edit_text(
        f"⏰ Выберите удобное время для даты {current_date}:\n"
        f"(можно выбрать несколько вариантов)",
        reply_markup=time_selection_keyboard(date_idx, selected_times, user['timezone'])
    )
    
    await callback.answer()

@router.callback_query(CreateMeeting.choosing_time, F.data == "time_done")
async def time_done_callback(callback: CallbackQuery, state: FSMContext, db: Database):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} нажал кнопку 'Далее'")
    logger.info(f"Текущее состояние: {await state.get_state()}")
    
    if user_id not in temp_meeting_data:
        await callback.answer("Ошибка! Начните создание встречи заново.")
        await state.clear()
        return
    
    selected_dates = temp_meeting_data[user_id]['selected_dates']
    current_idx = temp_meeting_data[user_id]['current_date_idx']
    
    logger.info(f"Выбранные даты: {selected_dates}")
    logger.info(f"Текущий индекс: {current_idx}")
    
    if current_idx >= len(selected_dates):
        await callback.answer("Ошибка: индекс даты вне диапазона")
        return
    
    current_date = selected_dates[current_idx]
    logger.info(f"Текущая дата: {current_date}")
    
    selected_times_for_current = temp_meeting_data[user_id]['selected_times'].get(current_date, [])
    logger.info(f"Выбранное время для {current_date}: {selected_times_for_current}")
    
    if not selected_times_for_current:
        await callback.answer("❌ Выберите хотя бы один вариант времени!")
        return
    
    # Получаем пользователя для его часового пояса
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("Ошибка! Пользователь не найден.")
        return
    
    if current_idx + 1 < len(selected_dates):
        next_idx = current_idx + 1
        temp_meeting_data[user_id]['current_date_idx'] = next_idx
        next_date = selected_dates[next_idx]
        logger.info(f"Переход к следующей дате: {next_date}")
        
        available_dates = get_available_dates()
        date_idx = None
        for i, d in enumerate(available_dates):
            if d.strftime("%d.%m.%Y") == next_date:
                date_idx = i
                break
        
        if date_idx is None:
            await callback.answer("Ошибка: следующая дата не найдена")
            return
        
        logger.info(f"Индекс следующей даты: {date_idx}")
        
        selected_times = temp_meeting_data[user_id]['selected_times'].get(next_date, [])
        logger.info(f"Ранее выбранное время для {next_date}: {selected_times}")
        
        await callback.message.edit_text(
            f"⏰ Выберите удобное время для даты {next_date}:",
            reply_markup=time_selection_keyboard(date_idx, selected_times, user['timezone'])
        )
    else:
        logger.info(f"Все даты обработаны, сохраняем встречу")
        await save_created_meeting(callback.message, state, db, user_id)
    
    await callback.answer()

@router.callback_query(CreateMeeting.choosing_time, F.data.startswith("time_"))
async def select_time_callback(callback: CallbackQuery, state: FSMContext, db: Database):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал время с callback_data: {callback.data}")
    
    if user_id not in temp_meeting_data:
        await callback.answer("Ошибка! Начните создание встречи заново.")
        await state.clear()
        return
    
    # Получаем пользователя для часового пояса
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("Ошибка! Пользователь не найден.")
        return
    
    data = callback.data
    data_without_prefix = data.replace("time_", "")
    parts = data_without_prefix.split("_", 1)
    
    if len(parts) != 2:
        await callback.answer("Ошибка формата данных")
        return
    
    try:
        date_idx = int(parts[0])
        time_str = parts[1]
        logger.info(f"Индекс даты: {date_idx}, время: {time_str}")
    except ValueError:
        await callback.answer("Ошибка обработки данных")
        return
    
    available_dates = get_available_dates()
    if date_idx >= len(available_dates):
        await callback.answer("Ошибка: дата не найдена")
        return
    
    date = available_dates[date_idx]
    date_str = date.strftime("%d.%m.%Y")
    logger.info(f"Выбрана дата: {date_str}")
    
    if date_str not in temp_meeting_data[user_id]['selected_times']:
        temp_meeting_data[user_id]['selected_times'][date_str] = []
        logger.info(f"Инициализирован список времени для даты {date_str}")
    
    if time_str in temp_meeting_data[user_id]['selected_times'][date_str]:
        temp_meeting_data[user_id]['selected_times'][date_str].remove(time_str)
        logger.info(f"Время {time_str} удалено из выбранных")
    else:
        temp_meeting_data[user_id]['selected_times'][date_str].append(time_str)
        logger.info(f"Время {time_str} добавлено в выбранные")
    
    logger.info(f"Текущие выбранные времена для {date_str}: {temp_meeting_data[user_id]['selected_times'][date_str]}")
    
    # Обновляем сообщение с учетом часового пояса
    await callback.message.edit_text(
        f"⏰ Выберите удобное время для даты {date_str}:",
        reply_markup=time_selection_keyboard(
            date_idx,
            temp_meeting_data[user_id]['selected_times'].get(date_str, []),
            user['timezone']
        )
    )
    
    await callback.answer()

async def save_created_meeting(message: Message, state: FSMContext, db: Database, user_id: int):
    logger.info(f"Начало сохранения встречи для пользователя {user_id}")
    
    data = await state.get_data()
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Ошибка! Пользователь не найден.")
        await state.clear()
        if user_id in temp_meeting_data:
            del temp_meeting_data[user_id]
        return
    
    try:
        meeting_id = await db.create_meeting(
            creator_id=user['id'],
            title=data['title'],
            description=data.get('description', '')
        )
        logger.info(f"Создана встреча с ID: {meeting_id}")
        
        user_tz = user['timezone']
        selected_dates = temp_meeting_data[user_id]['selected_dates']
        selected_times = temp_meeting_data[user_id]['selected_times']
        
        logger.info(f"Часовой пояс пользователя: {user_tz}")
        logger.info(f"Выбранные даты: {selected_dates}")
        logger.info(f"Выбранные времена: {selected_times}")
        
        options_added = 0
        for date_str in selected_dates:
            for time_str in selected_times.get(date_str, []):
                local_dt_str = f"{date_str} {time_str}"
                logger.info(f"Добавление варианта: {local_dt_str}")
                
                utc_dt_str = local_to_utc(local_dt_str, user_tz)
                option_text = f"{date_str} {time_str}"
                
                await db.add_meeting_option(meeting_id, utc_dt_str, option_text)
                options_added += 1
        
        logger.info(f"Добавлено вариантов времени: {options_added}")
        
        bot_username = (await message.bot.me()).username
        invite_link = f"https://t.me/{bot_username}?start=meeting_{meeting_id}"
        logger.info(f"Сгенерирована ссылка: {invite_link}")
        
        await message.answer(
            f"✅ Встреча \"{data['title']}\" успешно создана!\n\n"
            f"Добавлено вариантов времени: {options_added}\n\n"
            f"🔗 Ссылка-приглашение для участников:\n"
            f"{invite_link}\n\n"
            f"Отправьте эту ссылку участникам, чтобы они могли проголосовать.",
            reply_markup=main_menu_keyboard()
        )
        
        logger.info(f"Встреча {meeting_id} успешно создана пользователем {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении встречи: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при создании встречи. Попробуйте еще раз.",
            reply_markup=main_menu_keyboard()
        )
    finally:
        await state.clear()
        if user_id in temp_meeting_data:
            del temp_meeting_data[user_id]
            logger.info(f"Временные данные для пользователя {user_id} очищены")