from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database.db import Database
from keyboards.reply import main_menu_keyboard
from keyboards.inline import timezone_keyboard

router = Router()

@router.message(F.text == "🚀 Старт")
async def start_button_handler(message: Message, db: Database, state: FSMContext):
    from handlers.start import cmd_start
    await cmd_start(message, None, db, state)

@router.message(F.text == "📅 Создать встречу")
async def create_meeting_button(message: Message, db: Database, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer(
            "❌ Сначала нужно выбрать часовой пояс!\n\n"
            "Выберите ваш часовой пояс:",
            reply_markup=timezone_keyboard()
        )
        return
    
    from handlers.create_meeting import start_creating_meeting
    await start_creating_meeting(message, db, state)

@router.message(F.text == "📋 Мои встречи")
async def my_meetings_button(message: Message, db: Database, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer(
            "❌ Сначала нужно выбрать часовой пояс!\n\n"
            "Выберите ваш часовой пояс:",
            reply_markup=timezone_keyboard()
        )
        return
    
    from handlers.my_meetings import show_my_meetings
    await show_my_meetings(message, db)

@router.message(Command("menu"))
async def cmd_menu(message: Message, db: Database, state: FSMContext):
    await state.clear()
    
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer(
            "❌ Сначала нужно выбрать часовой пояс!\n\n"
            "Выберите ваш часовой пояс:",
            reply_markup=timezone_keyboard()
        )
        return
    
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard()
    )