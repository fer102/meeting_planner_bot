from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from database.db import Database
from keyboards.reply import main_menu_keyboard
from keyboards.inline import (
    meetings_list_keyboard, meeting_management_keyboard, 
    back_keyboard, reminder_keyboard, edit_options_keyboard,
    time_selection_keyboard, date_selection_keyboard
)
from states.meeting_states import BroadcastMessage, EditMeeting
from utils.time_helpers import utc_to_local, get_available_dates, get_available_times_for_date, local_to_utc, utc_now
import aiosqlite
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
router = Router()

temp_edit_data = {}

async def show_my_meetings(message: Message, db: Database):
    """Показывает список встреч пользователя"""
    try:
        user = await db.get_user(message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден.")
            return
        
        meetings = await db.get_meetings_by_user(user['id'])
        
        if not meetings:
            await message.answer(
                "У вас пока нет встреч.\n"
                "Создайте новую встречу через главное меню!",
                reply_markup=main_menu_keyboard()
            )
            return
        
        text = "📋 Ваши встречи:\n\n"
        for meeting in meetings:
            if meeting['finalized_option_id']:
                async with aiosqlite.connect(db.db_path) as conn:
                    cursor = await conn.execute(
                        "SELECT option_text FROM meeting_options WHERE id = ?",
                        (meeting['finalized_option_id'],)
                    )
                    opt = await cursor.fetchone()
                    final_time = f"✅ {opt[0]}" if opt else "⏳ Время не выбрано"
            else:
                final_time = "⏳ Голосование идет"
            
            title = meeting['title'][:30] + "..." if len(meeting['title']) > 30 else meeting['title']
            text += f"• {title} - {final_time}\n"
        
        await message.answer(
            text,
            reply_markup=meetings_list_keyboard(meetings, user['id'])
        )
    except Exception as e:
        logger.error(f"Ошибка при показе списка встреч: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при загрузке списка встреч.")

@router.callback_query(F.data.startswith("meeting_"))
async def show_meeting_details(callback: CallbackQuery, db: Database):
    """Показывает детали конкретной встречи"""
    try:
        meeting_id = int(callback.data.replace("meeting_", ""))
        logger.info(f"Пользователь {callback.from_user.id} просматривает встречу {meeting_id}")
        
        meeting = await db.get_meeting(meeting_id)
        user = await db.get_user(callback.from_user.id)
        
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
        
        creator = await db.get_user_by_id(meeting['creator_id'])
        is_creator = (creator and creator['telegram_id'] == callback.from_user.id)
        
        final_time_text = ""
        if meeting['finalized_option_id']:
            options = await db.get_meeting_options(meeting_id)
            for opt in options:
                if opt['id'] == meeting['finalized_option_id']:
                    final_time_text = f"\n✅ Подтвержденное время: {utc_to_local(opt['option_datetime'], user['timezone'])}"
                    break
        
        text = (
            f"📅 Встреча: {meeting['title']}\n"
            f"📝 Описание: {meeting['description'] or 'Нет описания'}"
            f"{final_time_text}\n\n"
            f"Выберите действие:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=meeting_management_keyboard(meeting_id, is_creator)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе деталей встречи: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("view_results_"))
async def view_results(callback: CallbackQuery, db: Database):
    """Просмотр результатов голосования"""
    try:
        meeting_id = int(callback.data.replace("view_results_", ""))
        logger.info(f"Пользователь {callback.from_user.id} просматривает результаты встречи {meeting_id}")
        
        results = await db.get_vote_counts(meeting_id)
        meeting = await db.get_meeting(meeting_id)
        
        if not results:
            await callback.answer("Пока нет голосов")
            return
        
        text = f"📊 Результаты голосования для встречи \"{meeting['title']}\":\n\n"
        
        for r in results:
            voters_text = f" (голосовали: {r['voters']})" if r['voters'] else ""
            text += f"• {r['option_text']}: {r['votes_count']} голосов{voters_text}\n"
        
        await callback.message.answer(
            text,
            reply_markup=back_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе результатов: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("delete_"))
async def delete_single_meeting(callback: CallbackQuery, db: Database):
    """Удаление конкретной встречи"""
    try:
        if callback.data == "delete_past_meetings" or callback.data == "unique_past_delete":
            return
        
        meeting_id = int(callback.data.replace("delete_", ""))
        logger.info(f"Пользователь {callback.from_user.id} пытается удалить встречу {meeting_id}")
        
        meeting = await db.get_meeting(meeting_id)
        
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
        
        creator = await db.get_user_by_id(meeting['creator_id'])
        if not creator or creator['telegram_id'] != callback.from_user.id:
            await callback.answer("Только создатель может удалить встречу")
            return
        
        await db.delete_meeting(meeting_id)
        
        await callback.message.edit_text(
            "✅ Встреча успешно удалена."
        )
        await callback.answer()
    except ValueError:
        pass
    except Exception as e:
        logger.error(f"Ошибка при удалении встречи: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "unique_past_delete")
async def delete_past_meetings_handler(callback: CallbackQuery, db: Database):
    """Удаление всех прошедших встреч ТОЛЬКО ДЛЯ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        logger.info(f"Пользователь {callback.from_user.id} запросил удаление своих прошедших встреч")
        
        # Показываем, какие встречи будут удалены (только для этого пользователя)
        async with aiosqlite.connect(db.db_path) as conn:
            now = datetime.now(timezone.utc).isoformat()
            two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            
            cursor = await conn.execute(
                """SELECT m.id, m.title, m.created_at, m.finalized_option_id,
                          mo.option_datetime as finalized_time
                   FROM meetings m
                   LEFT JOIN meeting_options mo ON m.finalized_option_id = mo.id
                   WHERE m.creator_id = ? 
                   AND (
                       (m.finalized_option_id IS NOT NULL AND mo.option_datetime < ?)
                       OR
                       (m.finalized_option_id IS NULL AND m.created_at < ?)
                   )""",
                (user['id'], now, two_hours_ago)
            )
            rows = await cursor.fetchall()
            
            if rows:
                preview_text = "Будут удалены следующие ваши встречи:\n\n"
                for row in rows:
                    if row[3]:
                        preview_text += f"• {row[1]} (прошедшая, время: {row[4]})\n"
                    else:
                        preview_text += f"• {row[1]} (без подтверждения, создана: {row[2]})\n"
                
                await callback.message.answer(preview_text)
        
        deleted_count = await db.delete_past_meetings(user['id'])
        
        if deleted_count > 0:
            await callback.answer(f"✅ Удалено {deleted_count} ваших прошедших встреч")
        else:
            await callback.answer("ℹ️ Нет ваших прошедших встреч для удаления")
        
        meetings = await db.get_meetings_by_user(user['id'])
        
        if not meetings:
            await callback.message.edit_text(
                "У вас пока нет встреч.\n"
                "Создайте новую встречу через главное меню!"
            )
            return
        
        text = "📋 Ваши встречи:\n\n"
        for meeting in meetings:
            if meeting['finalized_option_id']:
                async with aiosqlite.connect(db.db_path) as conn:
                    cursor = await conn.execute(
                        "SELECT option_text FROM meeting_options WHERE id = ?",
                        (meeting['finalized_option_id'],)
                    )
                    opt = await cursor.fetchone()
                    final_time = f"✅ {opt[0]}" if opt else "⏳ Время не выбрано"
            else:
                final_time = "⏳ Голосование идет"
            
            title = meeting['title'][:30] + "..." if len(meeting['title']) > 30 else meeting['title']
            text += f"• {title} - {final_time}\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=meetings_list_keyboard(meetings, user['id'])
        )
        
    except Exception as e:
        logger.error(f"Ошибка при удалении прошедших встреч: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("finalize_"))
async def finalize_meeting(callback: CallbackQuery, db: Database):
    """Подтверждение финального времени встречи"""
    try:
        meeting_id = int(callback.data.replace("finalize_", ""))
        logger.info(f"Пользователь {callback.from_user.id} финализирует встречу {meeting_id}")
        
        meeting = await db.get_meeting(meeting_id)
        
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
        
        creator = await db.get_user_by_id(meeting['creator_id'])
        if not creator or creator['telegram_id'] != callback.from_user.id:
            await callback.answer("Только создатель может подтвердить время")
            return
        
        if meeting['finalized_option_id']:
            await callback.answer("Время уже подтверждено")
            return
        
        results = await db.get_vote_counts(meeting_id)
        
        if not results:
            await callback.answer("Пока нет голосов для выбора времени")
            return
        
        sorted_results = sorted(results, key=lambda x: x['votes_count'], reverse=True)
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        
        for r in sorted_results:
            voters_text = f" ({r['voters']})" if r['voters'] else ""
            builder.button(
                text=f"{r['option_text']} - {r['votes_count']} гол.{voters_text}",
                callback_data=f"confirm_{meeting_id}_{r['id']}"
            )
        
        builder.button(text="🔙 Назад", callback_data=f"meeting_{meeting_id}")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "✅ Выберите финальное время для встречи:",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при финализации встречи: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("confirm_"))
async def confirm_final_time(callback: CallbackQuery, db: Database):
    """Подтверждение выбранного финального времени"""
    try:
        parts = callback.data.split("_")
        if len(parts) != 3:
            logger.error(f"Неверный формат callback_data: {callback.data}")
            await callback.answer("Ошибка формата данных")
            return
            
        meeting_id = int(parts[1])
        option_id = int(parts[2])
        
        logger.info(f"Пользователь {callback.from_user.id} подтверждает время {option_id} для встречи {meeting_id}")
        
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
            
        creator = await db.get_user_by_id(meeting['creator_id'])
        if not creator or creator['telegram_id'] != callback.from_user.id:
            await callback.answer("Только создатель может подтвердить время")
            return
        
        if meeting['finalized_option_id']:
            await callback.answer("Время уже подтверждено")
            return
        
        await db.set_finalized_option(meeting_id, option_id)
        
        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT option_text, option_datetime FROM meeting_options WHERE id = ?", 
                (option_id,)
            )
            option = await cursor.fetchone()
            option_text = option['option_text'] if option else "Неизвестное время"
            option_datetime = option['option_datetime'] if option else ""
        
        participants = await db.get_meeting_participants(meeting_id)
        
        creator_user = await db.get_user_by_id(meeting['creator_id'])
        
        sent_count = 0
        for participant in participants:
            try:
                user_tz = participant['timezone']
                local_time = utc_to_local(option_datetime, user_tz) if option_datetime else option_text
                
                await callback.bot.send_message(
                    participant['telegram_id'],
                    f"✅ Время для встречи \"{meeting['title']}\" подтверждено!\n\n"
                    f"📅 {local_time}\n\n"
                    f"Организатор: {creator_user['username'] or 'Неизвестно'}"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю {participant['telegram_id']}: {e}")
        
        user = await db.get_user(callback.from_user.id)
        local_time_for_creator = utc_to_local(option_datetime, user['timezone']) if option_datetime else option_text
        
        await callback.message.edit_text(
            f"✅ Время подтверждено!\n\n"
            f"Встреча: {meeting['title']}\n"
            f"Время: {local_time_for_creator}\n\n"
            f"Уведомления отправлены {sent_count} из {len(participants)} участников."
        )
        
        logger.info(f"Время для встречи {meeting_id} подтверждено, уведомлено {sent_count} участников")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при подтверждении времени: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("remind_"))
async def setup_reminder(callback: CallbackQuery, db: Database):
    """Настройка напоминания"""
    try:
        data = callback.data.replace("remind_", "")
        
        if "_" in data:
            parts = data.split("_")
            meeting_id = int(parts[0])
            minutes = int(parts[1])
            
            user = await db.get_user(callback.from_user.id)
            if not user:
                await callback.answer("Пользователь не найден")
                return
            
            await db.add_reminder(meeting_id, user['id'], minutes)
            
            await callback.message.edit_text(
                f"✅ Напоминание установлено за {minutes} минут до встречи.",
                reply_markup=back_keyboard()
            )
        else:
            meeting_id = int(data)
            await callback.message.edit_text(
                "⏰ Выберите, за сколько времени напомнить:",
                reply_markup=reminder_keyboard(meeting_id)
            )
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при установке напоминания: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("broadcast_"))
async def broadcast_message(callback: CallbackQuery, state: FSMContext, db: Database):
    """Начало рассылки сообщения участникам"""
    try:
        meeting_id = int(callback.data.replace("broadcast_", ""))
        meeting = await db.get_meeting(meeting_id)
        
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
        
        creator = await db.get_user_by_id(meeting['creator_id'])
        if not creator or creator['telegram_id'] != callback.from_user.id:
            await callback.answer("Только создатель может отправлять сообщения")
            return
        
        await state.update_data(broadcast_meeting_id=meeting_id)
        await state.set_state(BroadcastMessage.typing_message)
        
        await callback.message.edit_text(
            f"📨 Введите сообщение для отправки всем участникам встречи \"{meeting['title']}\":"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале рассылки: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.message(BroadcastMessage.typing_message)
async def process_broadcast_message(message: Message, state: FSMContext, db: Database):
    """Обработка ввода сообщения для рассылки"""
    try:
        data = await state.get_data()
        meeting_id = data.get('broadcast_meeting_id')
        
        if not meeting_id:
            await message.answer("❌ Ошибка: не найден ID встречи")
            await state.clear()
            return
        
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await message.answer("❌ Встреча не найдена")
            await state.clear()
            return
        
        participants = await db.get_meeting_participants(meeting_id)
        
        sent_count = 0
        for participant in participants:
            try:
                await message.bot.send_message(
                    participant['telegram_id'],
                    f"📨 Сообщение от организатора встречи \"{meeting['title']}\":\n\n{message.text}"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю {participant['telegram_id']}: {e}")
        
        await message.answer(
            f"✅ Сообщение отправлено {sent_count} из {len(participants)} участников.",
            reply_markup=main_menu_keyboard()
        )
        
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка при отправке рассылки: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при отправке сообщения.")
        await state.clear()

@router.callback_query(F.data.startswith("edit_"))
async def edit_meeting(callback: CallbackQuery, state: FSMContext, db: Database):
    """Редактирование встречи"""
    try:
        meeting_id = int(callback.data.replace("edit_", ""))
        logger.info(f"Пользователь {callback.from_user.id} редактирует встречу {meeting_id}")
        
        meeting = await db.get_meeting(meeting_id)
        
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
        
        creator = await db.get_user_by_id(meeting['creator_id'])
        if not creator or creator['telegram_id'] != callback.from_user.id:
            await callback.answer("Только создатель может редактировать встречу")
            return
        
        if meeting['finalized_option_id']:
            await callback.answer("❌ Нельзя редактировать подтвержденную встречу")
            return
        
        options = await db.get_meeting_options(meeting_id)
        
        temp_edit_data[callback.from_user.id] = {
            'meeting_id': meeting_id,
            'options': options
        }
        
        await state.set_state(EditMeeting.choosing_option)
        logger.info(f"Пользователь {callback.from_user.id} переведен в состояние EditMeeting.choosing_option")
        
        await callback.message.edit_text(
            "✏️ Редактирование вариантов времени встречи\n\n"
            "Нажмите на вариант, чтобы удалить его, или добавьте новый:",
            reply_markup=edit_options_keyboard(meeting_id, options)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при редактировании встречи: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(EditMeeting.choosing_option, F.data.startswith("delete_option_"))
async def delete_option(callback: CallbackQuery, state: FSMContext, db: Database):
    """Удаление варианта времени"""
    try:
        # Логируем полученный callback
        logger.info(f"DELETE_OPTION вызван с callback_data: {callback.data}")
        
        # Проверяем текущее состояние
        current_state = await state.get_state()
        logger.info(f"Текущее состояние: {current_state}")
        
        # Проверяем, соответствует ли состояние
        if current_state != EditMeeting.choosing_option:
            logger.warning(f"Неверное состояние: {current_state}, ожидалось: {EditMeeting.choosing_option}")
            # Пробуем восстановить состояние
            await state.set_state(EditMeeting.choosing_option)
            logger.info("Состояние восстановлено")
        
        parts = callback.data.split("_")
        if len(parts) != 4:
            logger.error(f"Неверный формат callback_data: {callback.data}")
            await callback.answer("Ошибка формата данных")
            return
            
        meeting_id = int(parts[2])
        option_id = int(parts[3])
        
        logger.info(f"Пользователь {callback.from_user.id} удаляет вариант {option_id} из встречи {meeting_id}")
        
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
            
        creator = await db.get_user_by_id(meeting['creator_id'])
        if not creator or creator['telegram_id'] != callback.from_user.id:
            await callback.answer("Только создатель может удалять варианты")
            return
        
        if meeting['finalized_option_id']:
            await callback.answer("❌ Нельзя удалять варианты после подтверждения времени")
            return
        
        # Удаляем вариант и связанные голоса
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute("DELETE FROM votes WHERE option_id = ?", (option_id,))
            await conn.execute("DELETE FROM meeting_options WHERE id = ?", (option_id,))
            await conn.commit()
            logger.info(f"Вариант {option_id} и связанные голоса удалены")
        
        # Получаем обновленный список опций
        options = await db.get_meeting_options(meeting_id)
        
        # Обновляем сообщение
        await callback.message.edit_text(
            "✏️ Редактирование вариантов времени встречи\n\n"
            "Нажмите на вариант, чтобы удалить его, или добавьте новый:",
            reply_markup=edit_options_keyboard(meeting_id, options)
        )
        
        await callback.answer("✅ Вариант удален")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении варианта: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(EditMeeting.choosing_option, F.data.startswith("add_option_"))
async def add_option_start(callback: CallbackQuery, state: FSMContext, db: Database):
    """Начало добавления нового варианта"""
    try:
        # Логируем полученный callback
        logger.info(f"ADD_OPTION_START вызван с callback_data: {callback.data}")
        
        meeting_id = int(callback.data.replace("add_option_", ""))
        
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
            
        if meeting['finalized_option_id']:
            await callback.answer("❌ Нельзя добавлять варианты после подтверждения времени")
            return
        
        await state.update_data(edit_meeting_id=meeting_id)
        await state.set_state(EditMeeting.adding_new_time)
        logger.info(f"Пользователь {callback.from_user.id} переведен в состояние EditMeeting.adding_new_time")
        
        user = await db.get_user(callback.from_user.id)
        temp_edit_data[callback.from_user.id] = {
            'meeting_id': meeting_id,
            'selected_dates': [],
            'selected_times': {},
            'current_date_idx': 0
        }
        
        await callback.message.edit_text(
            "📅 Выберите дату для нового варианта времени:",
            reply_markup=date_selection_keyboard(user_timezone=user['timezone'])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале добавления варианта: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(EditMeeting.adding_new_time, F.data.startswith("date_"))
async def add_option_date(callback: CallbackQuery, state: FSMContext, db: Database):
    """Выбор даты для нового варианта"""
    try:
        # Логируем полученный callback
        logger.info(f"ADD_OPTION_DATE вызван с callback_data: {callback.data}")
        
        user_id = callback.from_user.id
        
        if user_id not in temp_edit_data:
            await callback.answer("Ошибка! Начните редактирование заново.")
            await state.clear()
            return
        
        user = await db.get_user(user_id)
        if not user:
            await callback.answer("Ошибка! Пользователь не найден.")
            return
        
        try:
            date_idx = int(callback.data.replace("date_", ""))
        except ValueError:
            await callback.answer("Ошибка обработки данных")
            return
        
        available_dates = get_available_dates(user['timezone'])
        if date_idx >= len(available_dates):
            await callback.answer("Ошибка: дата не найдена")
            return
        
        date_str = available_dates[date_idx].strftime("%d.%m.%Y")
        
        if date_str in temp_edit_data[user_id]['selected_dates']:
            temp_edit_data[user_id]['selected_dates'].remove(date_str)
        else:
            temp_edit_data[user_id]['selected_dates'].append(date_str)
        
        await callback.message.edit_text(
            "📅 Выберите дату для нового варианта времени:",
            reply_markup=date_selection_keyboard(temp_edit_data[user_id]['selected_dates'], user['timezone'])
        )
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при выборе даты: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(EditMeeting.adding_new_time, F.data == "dates_done")
async def add_option_dates_done(callback: CallbackQuery, state: FSMContext, db: Database):
    """Завершение выбора дат"""
    try:
        # Логируем полученный callback
        logger.info(f"DATES_DONE вызван с callback_data: {callback.data}")
        
        user_id = callback.from_user.id
        
        if user_id not in temp_edit_data:
            await callback.answer("Ошибка! Начните редактирование заново.")
            await state.clear()
            return
        
        user = await db.get_user(user_id)
        if not user:
            await callback.answer("Ошибка! Пользователь не найден.")
            return
        
        selected_dates = temp_edit_data[user_id]['selected_dates']
        
        if not selected_dates:
            await callback.answer("❌ Выберите хотя бы одну дату!")
            return
        
        temp_edit_data[user_id]['current_date_idx'] = 0
        current_date = selected_dates[0]
        
        available_dates = get_available_dates(user['timezone'])
        date_idx = None
        for i, d in enumerate(available_dates):
            if d.strftime("%d.%m.%Y") == current_date:
                date_idx = i
                break
        
        if date_idx is None:
            await callback.answer("Ошибка с датой!")
            return
        
        selected_times = temp_edit_data[user_id]['selected_times'].get(current_date, [])
        
        await callback.message.edit_text(
            f"⏰ Выберите время для даты {current_date}:",
            reply_markup=time_selection_keyboard(date_idx, selected_times, user['timezone'])
        )
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при завершении выбора дат: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(EditMeeting.adding_new_time, F.data.startswith("time_"))
async def add_option_time(callback: CallbackQuery, state: FSMContext, db: Database):
    """Выбор времени для нового варианта"""
    try:
        # Логируем полученный callback
        logger.info(f"ADD_OPTION_TIME вызван с callback_data: {callback.data}")
        
        user_id = callback.from_user.id
        
        if user_id not in temp_edit_data:
            await callback.answer("Ошибка! Начните редактирование заново.")
            await state.clear()
            return
        
        user = await db.get_user(user_id)
        if not user:
            await callback.answer("Ошибка! Пользователь не найден.")
            return
        
        data = callback.data
        
        # Проверяем, не является ли это кнопкой "Далее"
        if data == "time_done":
            logger.info("Получена команда time_done, вызываем соответствующий хендлер")
            # Вместо return вызываем нужный хендлер напрямую
            await add_option_time_done(callback, state, db)
            return
        
        # Парсим callback_data: time_{date_idx}_{time_str}
        data_without_prefix = data.replace("time_", "")
        
        # Разделяем на части
        parts = data_without_prefix.split("_", 1)
        if len(parts) != 2:
            logger.error(f"Неверный формат данных: {data_without_prefix}")
            await callback.answer("Ошибка формата данных")
            return
        
        try:
            date_idx = int(parts[0])
            time_str = parts[1]
            logger.info(f"Индекс даты: {date_idx}, время: {time_str}")
        except ValueError as e:
            logger.error(f"Ошибка преобразования данных: {e}")
            await callback.answer("Ошибка обработки данных")
            return
        
        available_dates = get_available_dates(user['timezone'])
        if date_idx >= len(available_dates):
            await callback.answer("Ошибка: дата не найдена")
            return
        
        date = available_dates[date_idx]
        date_str = date.strftime("%d.%m.%Y")
        
        if date_str not in temp_edit_data[user_id]['selected_times']:
            temp_edit_data[user_id]['selected_times'][date_str] = []
        
        if time_str in temp_edit_data[user_id]['selected_times'][date_str]:
            temp_edit_data[user_id]['selected_times'][date_str].remove(time_str)
            action = "удалено из"
        else:
            temp_edit_data[user_id]['selected_times'][date_str].append(time_str)
            action = "добавлено в"
        
        logger.info(f"Время {time_str} {action} выбранных для даты {date_str}")
        logger.info(f"Текущие выбранные времена для {date_str}: {temp_edit_data[user_id]['selected_times'][date_str]}")
        
        await callback.message.edit_text(
            f"⏰ Выберите время для даты {date_str}:",
            reply_markup=time_selection_keyboard(
                date_idx,
                temp_edit_data[user_id]['selected_times'].get(date_str, []),
                user['timezone']
            )
        )
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при выборе времени: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(EditMeeting.adding_new_time, F.data == "time_done")
async def add_option_time_done(callback: CallbackQuery, state: FSMContext, db: Database):
    """Завершение выбора времени для текущей даты"""
    try:
        # Логируем полученный callback
        logger.info(f"TIME_DONE вызван с callback_data: {callback.data}")
        
        user_id = callback.from_user.id
        logger.info(f"Пользователь {user_id} нажал 'Далее' при добавлении вариантов")
        
        # Проверяем, есть ли временные данные
        if user_id not in temp_edit_data:
            logger.error(f"Временные данные не найдены для пользователя {user_id}")
            await callback.answer("Ошибка! Начните редактирование заново.")
            await state.clear()
            return
        
        # Проверяем, есть ли пользователь в базе
        user = await db.get_user(user_id)
        if not user:
            await callback.answer("Ошибка! Пользователь не найден.")
            return
        
        # Получаем данные
        selected_dates = temp_edit_data[user_id]['selected_dates']
        current_idx = temp_edit_data[user_id]['current_date_idx']
        
        logger.info(f"Выбранные даты: {selected_dates}")
        logger.info(f"Текущий индекс: {current_idx}")
        
        # Проверяем индекс
        if current_idx >= len(selected_dates):
            logger.error(f"Индекс {current_idx} вне диапазона дат {selected_dates}")
            await callback.answer("Ошибка: индекс даты вне диапазона")
            return
        
        current_date = selected_dates[current_idx]
        
        # Проверяем, выбрано ли время для текущей даты
        selected_times_for_current = temp_edit_data[user_id]['selected_times'].get(current_date, [])
        logger.info(f"Выбранное время для {current_date}: {selected_times_for_current}")
        
        if not selected_times_for_current:
            await callback.answer("❌ Выберите хотя бы один вариант времени!")
            return
        
        # Переходим к следующей дате или сохраняем
        if current_idx + 1 < len(selected_dates):
            # Переходим к следующей дате
            next_idx = current_idx + 1
            temp_edit_data[user_id]['current_date_idx'] = next_idx
            next_date = selected_dates[next_idx]
            logger.info(f"Переход к следующей дате: {next_date}")
            
            available_dates = get_available_dates(user['timezone'])
            date_idx = None
            for i, d in enumerate(available_dates):
                if d.strftime("%d.%m.%Y") == next_date:
                    date_idx = i
                    break
            
            if date_idx is None:
                logger.error(f"Следующая дата {next_date} не найдена")
                await callback.answer("Ошибка: следующая дата не найдена")
                return
            
            selected_times = temp_edit_data[user_id]['selected_times'].get(next_date, [])
            logger.info(f"Ранее выбранное время для {next_date}: {selected_times}")
            
            await callback.message.edit_text(
                f"⏰ Выберите время для даты {next_date}:",
                reply_markup=time_selection_keyboard(date_idx, selected_times, user['timezone'])
            )
        else:
            # Все даты обработаны - сохраняем новые варианты
            logger.info(f"Все даты обработаны, сохраняем новые варианты")
            await save_new_options(callback.message, state, db, user_id)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при обработке time_done: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

async def save_new_options(message: Message, state: FSMContext, db: Database, user_id: int):
    """Сохранение новых вариантов времени"""
    try:
        logger.info(f"Сохранение новых вариантов для пользователя {user_id}")
        
        data = await state.get_data()
        meeting_id = data.get('edit_meeting_id')
        
        if not meeting_id:
            logger.error(f"Meeting ID не найден в состоянии для пользователя {user_id}")
            await message.answer("❌ Ошибка: не найден ID встречи")
            await state.clear()
            if user_id in temp_edit_data:
                del temp_edit_data[user_id]
            return
        
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await message.answer("❌ Встреча не найдена")
            await state.clear()
            if user_id in temp_edit_data:
                del temp_edit_data[user_id]
            return
            
        creator = await db.get_user_by_id(meeting['creator_id'])
        if not creator or creator['telegram_id'] != user_id:
            await message.answer("❌ Только создатель может добавлять варианты")
            await state.clear()
            if user_id in temp_edit_data:
                del temp_edit_data[user_id]
            return
        
        if meeting['finalized_option_id']:
            await message.answer("❌ Нельзя добавлять варианты после подтверждения времени")
            await state.clear()
            if user_id in temp_edit_data:
                del temp_edit_data[user_id]
            return
        
        user = await db.get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            if user_id in temp_edit_data:
                del temp_edit_data[user_id]
            return
        
        selected_dates = temp_edit_data[user_id]['selected_dates']
        selected_times = temp_edit_data[user_id]['selected_times']
        
        if not selected_dates or not any(selected_times.values()):
            await message.answer("❌ Не выбрано ни одного варианта времени")
            await state.clear()
            if user_id in temp_edit_data:
                del temp_edit_data[user_id]
            return
        
        options_added = 0
        for date_str in selected_dates:
            for time_str in selected_times.get(date_str, []):
                local_dt_str = f"{date_str} {time_str}"
                utc_dt_str = local_to_utc(local_dt_str, user['timezone'])
                option_text = f"{date_str} {time_str}"
                
                await db.add_meeting_option(meeting_id, utc_dt_str, option_text)
                options_added += 1
                logger.info(f"Добавлен вариант: {option_text}")
        
        # Получаем обновленный список опций
        options = await db.get_meeting_options(meeting_id)
        
        # Возвращаемся к редактированию
        await message.answer(
            f"✅ Добавлено новых вариантов: {options_added}",
            reply_markup=edit_options_keyboard(meeting_id, options)
        )
        
        logger.info(f"Добавлено {options_added} новых вариантов к встрече {meeting_id}")
        
        # Очищаем временные данные
        if user_id in temp_edit_data:
            del temp_edit_data[user_id]
        
        # Возвращаем состояние к choosing_option
        await state.set_state(EditMeeting.choosing_option)
        logger.info(f"Пользователь {user_id} возвращен в состояние EditMeeting.choosing_option")
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении новых вариантов: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при сохранении.")
        await state.clear()
        if user_id in temp_edit_data:
            del temp_edit_data[user_id]

@router.callback_query(F.data.startswith("finish_edit_"))
async def finish_edit(callback: CallbackQuery, state: FSMContext, db: Database):
    """Завершение редактирования"""
    try:
        logger.info(f"FINISH_EDIT вызван с callback_data: {callback.data}")
        
        meeting_id = int(callback.data.replace("finish_edit_", ""))
        
        meeting = await db.get_meeting(meeting_id)
        user = await db.get_user(callback.from_user.id)
        
        creator = await db.get_user_by_id(meeting['creator_id'])
        is_creator = (creator and creator['telegram_id'] == callback.from_user.id)
        
        final_time_text = ""
        if meeting['finalized_option_id']:
            options = await db.get_meeting_options(meeting_id)
            for opt in options:
                if opt['id'] == meeting['finalized_option_id']:
                    final_time_text = f"\n✅ Подтвержденное время: {utc_to_local(opt['option_datetime'], user['timezone'])}"
                    break
        
        text = (
            f"📅 Встреча: {meeting['title']}\n"
            f"📝 Описание: {meeting['description'] or 'Нет описания'}"
            f"{final_time_text}\n\n"
            f"Выберите действие:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=meeting_management_keyboard(meeting_id, is_creator)
        )
        
        await state.clear()
        if callback.from_user.id in temp_edit_data:
            del temp_edit_data[callback.from_user.id]
        
        await callback.answer("✅ Редактирование завершено")
    except Exception as e:
        logger.error(f"Ошибка при завершении редактирования: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "back_to_meetings")
async def back_to_meetings(callback: CallbackQuery, db: Database):
    """Возврат к списку встреч"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        meetings = await db.get_meetings_by_user(user['id'])
        
        text = "📋 Ваши встречи:\n\n"
        for meeting in meetings:
            if meeting['finalized_option_id']:
                async with aiosqlite.connect(db.db_path) as conn:
                    cursor = await conn.execute(
                        "SELECT option_text FROM meeting_options WHERE id = ?",
                        (meeting['finalized_option_id'],)
                    )
                    opt = await cursor.fetchone()
                    final_time = f"✅ {opt[0]}" if opt else "⏳ Время не выбрано"
            else:
                final_time = "⏳ Голосование идет"
            
            title = meeting['title'][:30] + "..." if len(meeting['title']) > 30 else meeting['title']
            text += f"• {title} - {final_time}\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=meetings_list_keyboard(meetings, user['id'])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку встреч: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")