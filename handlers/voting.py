from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from database.db import Database
from keyboards.inline import meeting_options_keyboard, back_keyboard
from keyboards.reply import main_menu_keyboard
from utils.time_helpers import utc_to_local
import logging
import aiosqlite

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data.startswith("vote_"))
async def process_vote(callback: CallbackQuery, db: Database):
    """Обработка голосования за вариант"""
    try:
        option_id = int(callback.data.replace("vote_", ""))
        user = await db.get_user(callback.from_user.id)
        
        if not user:
            await callback.answer("Сначала зарегистрируйтесь через /start")
            return
        
        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT meeting_id FROM meeting_options WHERE id = ?", (option_id,)
            )
            option = await cursor.fetchone()
        
        if not option:
            await callback.answer("Ошибка: вариант не найден")
            return
        
        meeting_id = option['meeting_id']
        
        # Проверяем, не финализирована ли уже встреча
        meeting = await db.get_meeting(meeting_id)
        if meeting and meeting['finalized_option_id']:
            await callback.answer("❌ Голосование закрыто, время уже подтверждено")
            return
        
        user_votes = await db.get_user_votes(meeting_id, user['id'])
        
        if option_id in user_votes:
            await db.unvote(option_id, user['id'])
            await callback.answer("Голос убран ❌")
        else:
            await db.vote(option_id, user['id'])
            await callback.answer("Голос добавлен ✅")
        
        options = await db.get_meeting_options(meeting_id)
        user_votes = await db.get_user_votes(meeting_id, user['id'])
        
        for opt in options:
            opt['display_time'] = utc_to_local(opt['option_datetime'], user['timezone'])
        
        await callback.message.edit_reply_markup(
            reply_markup=meeting_options_keyboard(meeting_id, options, user_votes)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при голосовании: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("results_"))
async def show_results(callback: CallbackQuery, db: Database):
    """Показ промежуточных результатов голосования"""
    try:
        meeting_id = int(callback.data.replace("results_", ""))
        
        results = await db.get_vote_counts(meeting_id)
        meeting = await db.get_meeting(meeting_id)
        
        if not results:
            await callback.answer("Пока нет голосов")
            return
        
        text = f"📊 Промежуточные результаты для встречи \"{meeting['title']}\":\n\n"
        
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

@router.callback_query(F.data.startswith("done_voting_"))
async def done_voting(callback: CallbackQuery, state: FSMContext, db: Database):
    """Завершение голосования"""
    try:
        meeting_id = int(callback.data.replace("done_voting_", ""))
        
        # Проверяем, не финализирована ли уже встреча
        meeting = await db.get_meeting(meeting_id)
        if meeting and meeting['finalized_option_id']:
            await callback.answer("❌ Время уже подтверждено")
            return
        
        # Удаляем сообщение с голосованием
        await callback.message.delete()
        
        # Отправляем подтверждение
        await callback.message.answer(
            "✅ Спасибо за участие в голосовании!\n"
            "Организатор получит уведомление о результатах.",
            reply_markup=main_menu_keyboard()
        )
        
        logger.info(f"Пользователь {callback.from_user.id} завершил голосование в встрече {meeting_id}")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при завершении голосования: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("revote_"))
async def revote(callback: CallbackQuery, db: Database):
    """Переголосование для участников, которые уже голосовали"""
    try:
        meeting_id = int(callback.data.replace("revote_", ""))
        logger.info(f"Пользователь {callback.from_user.id} запросил переголосование в встрече {meeting_id}")
        
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer("Сначала зарегистрируйтесь через /start")
            return
        
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
        
        # Проверяем, не финализирована ли встреча
        if meeting['finalized_option_id']:
            await callback.answer("❌ Голосование закрыто, время уже подтверждено")
            return
        
        # Получаем обновленные варианты времени
        options = await db.get_meeting_options(meeting_id)
        
        if not options:
            await callback.answer("❌ У этой встречи нет вариантов времени для голосования.")
            return
        
        # Получаем текущие голоса пользователя (если есть)
        user_votes = await db.get_user_votes(meeting_id, user['id'])
        
        # Форматируем время для отображения в часовом поясе пользователя
        for opt in options:
            opt['display_time'] = utc_to_local(opt['option_datetime'], user['timezone'])
        
        await callback.message.answer(
            f"📅 Встреча: {meeting['title']}\n\n"
            f"Описание: {meeting['description'] or 'Нет описания'}\n\n"
            f"Варианты времени обновлены. Выберите удобные для вас варианты:",
            reply_markup=meeting_options_keyboard(meeting_id, options, user_votes)
        )
        
        await callback.answer("🔄 Переголосование")
        
    except Exception as e:
        logger.error(f"Ошибка при переголосовании: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("vote_now_"))
async def vote_now(callback: CallbackQuery, db: Database):
    """Начало голосования для участника, который еще не голосовал"""
    try:
        meeting_id = int(callback.data.replace("vote_now_", ""))
        logger.info(f"Пользователь {callback.from_user.id} начинает голосование в встрече {meeting_id}")
        
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer("Сначала зарегистрируйтесь через /start")
            return
        
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            await callback.answer("Встреча не найдена")
            return
        
        # Проверяем, не финализирована ли встреча
        if meeting['finalized_option_id']:
            await callback.answer("❌ Голосование закрыто, время уже подтверждено")
            return
        
        # Получаем варианты времени
        options = await db.get_meeting_options(meeting_id)
        
        if not options:
            await callback.answer("❌ У этой встречи нет вариантов времени для голосования.")
            return
        
        # Добавляем пользователя в участники, если ещё не добавлен
        await db.add_participant(meeting_id, user['id'])
        
        # Получаем текущие голоса пользователя
        user_votes = await db.get_user_votes(meeting_id, user['id'])
        
        # Форматируем время для отображения в часовом поясе пользователя
        for opt in options:
            opt['display_time'] = utc_to_local(opt['option_datetime'], user['timezone'])
        
        await callback.message.answer(
            f"📅 Встреча: {meeting['title']}\n\n"
            f"Описание: {meeting['description'] or 'Нет описания'}\n\n"
            f"Выберите удобные для вас варианты времени:",
            reply_markup=meeting_options_keyboard(meeting_id, options, user_votes)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при начале голосования: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")        