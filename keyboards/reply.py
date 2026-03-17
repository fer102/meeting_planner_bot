from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🚀 Старт")],
        [KeyboardButton(text="📅 Создать встречу")],
        [KeyboardButton(text="📋 Мои встречи")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def cancel_keyboard() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )