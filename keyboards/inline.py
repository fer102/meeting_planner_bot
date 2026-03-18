from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.time_helpers import (
    TIMEZONES, get_timezone_display, get_available_dates, 
    get_available_times_for_date, utc_now, utc_to_local_time
)
from datetime import datetime

def timezone_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора часового пояса"""
    builder = InlineKeyboardBuilder()
    
    for utc_offset, city in TIMEZONES.items():
        display_text = get_timezone_display(utc_offset)
        builder.button(
            text=display_text,
            callback_data=f"tz_{utc_offset}"
        )
    
    builder.adjust(2)
    return builder.as_markup()

def date_selection_keyboard(selected_dates: list = None, user_timezone: str = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора дат
    Автоматически скрывает сегодняшнюю дату, если на неё нет доступного времени
    """
    if selected_dates is None:
        selected_dates = []
    
    builder = InlineKeyboardBuilder()
    available_dates = get_available_dates(user_timezone)
    
    days_map = {
        0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"
    }
    
    for i, date in enumerate(available_dates):
        date_str = date.strftime("%d.%m.%Y")
        day_of_week = days_map.get(date.weekday(), "")
        
        if date_str in selected_dates:
            text = f"✅ {date_str} ({day_of_week})"
        else:
            text = f"🔘 {date_str} ({day_of_week})"
        
        builder.button(text=text, callback_data=f"date_{i}")
    
    builder.button(text="✅ Готово", callback_data="dates_done")
    builder.adjust(1)
    return builder.as_markup()

def time_selection_keyboard(date_idx: int, selected_times: list = None, user_timezone: str = "UTC+3") -> InlineKeyboardMarkup:
    """Клавиатура для выбора времени для конкретной даты с учетом часового пояса пользователя"""
    if selected_times is None:
        selected_times = []
    
    builder = InlineKeyboardBuilder()
    available_dates = get_available_dates(user_timezone)
    
    if date_idx >= len(available_dates):
        builder.button(text="❌ Ошибка", callback_data="ignore")
        return builder.as_markup()
    
    date = available_dates[date_idx]
    times = get_available_times_for_date(date, user_timezone)
    
    for time_str in times:
        if time_str in selected_times:
            text = f"✅ {time_str}"
        else:
            text = f"🔘 {time_str}"
        
        builder.button(text=text, callback_data=f"time_{date_idx}_{time_str}")
    
    builder.button(text="⏩ Далее", callback_data="time_done")
    builder.adjust(3, 1)
    return builder.as_markup()

def meeting_options_keyboard(meeting_id: int, options: list, user_votes: list = None) -> InlineKeyboardMarkup:
    """Клавиатура для голосования по вариантам времени с кнопкой переголосования"""
    if user_votes is None:
        user_votes = []
    
    builder = InlineKeyboardBuilder()
    
    options_by_day = {}
    for opt in options:
        if 'display_time' in opt:
            day_part = opt['display_time'].split()[0]
        else:
            dt = datetime.fromisoformat(opt['option_datetime'].replace('Z', '+00:00'))
            day_part = dt.strftime("%d.%m.%Y")
        
        if day_part not in options_by_day:
            options_by_day[day_part] = []
        options_by_day[day_part].append(opt)
    
    for day, day_options in options_by_day.items():
        builder.button(text=f"--- {day} ---", callback_data="ignore")
        
        for opt in day_options:
            opt_id = opt['id']
            
            if 'display_time' in opt:
                time_part = opt['display_time'].split()[1]
                display_text = f"{time_part}"
            else:
                dt = datetime.fromisoformat(opt['option_datetime'].replace('Z', '+00:00'))
                display_text = dt.strftime("%H:%M")
            
            if opt_id in user_votes:
                text = f"✅ {display_text}"
            else:
                text = f"🔘 {display_text}"
            
            builder.button(text=text, callback_data=f"vote_{opt_id}")
    
    # Добавляем кнопки управления
    builder.button(text="📊 Промежуточные результаты", callback_data=f"results_{meeting_id}")
    builder.button(text="✅ Завершить голосование", callback_data=f"done_voting_{meeting_id}")
    
    # Добавляем кнопку переголосования, если пользователь уже голосовал
    if user_votes:
        builder.button(text="🔄 Переголосовать", callback_data=f"revote_{meeting_id}")
    
    builder.adjust(1)
    return builder.as_markup()

def meeting_management_keyboard(meeting_id: int, is_creator: bool, has_voted: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура управления встречей
    
    Args:
        meeting_id: ID встречи
        is_creator: является ли пользователь создателем
        has_voted: голосовал ли пользователь (для участников)
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📊 Результаты", callback_data=f"view_results_{meeting_id}")
    
    if is_creator:
        builder.button(text="✏️ Изменить варианты", callback_data=f"edit_{meeting_id}")
        builder.button(text="📨 Сообщение участникам", callback_data=f"broadcast_{meeting_id}")
        builder.button(text="🗑 Удалить встречу", callback_data=f"delete_{meeting_id}")
        builder.button(text="✅ Подтвердить время", callback_data=f"finalize_{meeting_id}")
    else:
        # Для участников
        if has_voted:
            builder.button(text="🔄 Переголосовать", callback_data=f"revote_{meeting_id}")
        else:
            builder.button(text="🗳 Голосовать", callback_data=f"vote_now_{meeting_id}")
    
    builder.button(text="⏰ Напомнить мне", callback_data=f"remind_{meeting_id}")
    builder.button(text="🔙 Назад", callback_data="back_to_meetings")
    
    builder.adjust(1)
    return builder.as_markup()

def reminder_keyboard(meeting_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора напоминания"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="За 1 час", callback_data=f"remind_{meeting_id}_60")
    builder.button(text="За 30 минут", callback_data=f"remind_{meeting_id}_30")
    builder.button(text="За 10 минут", callback_data=f"remind_{meeting_id}_10")
    builder.button(text="🔙 Назад", callback_data=f"meeting_{meeting_id}")
    
    builder.adjust(1)
    return builder.as_markup()

def back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back")
    return builder.as_markup()

def meetings_list_keyboard(meetings: list, user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура со списком встреч"""
    builder = InlineKeyboardBuilder()
    
    for meeting in meetings:
        title = meeting['title'][:20] + "..." if len(meeting['title']) > 20 else meeting['title']
        builder.button(
            text=f"{title}",
            callback_data=f"meeting_{meeting['id']}"
        )
    
    builder.button(text="🗑 Удалить прошедшие встречи", callback_data="unique_past_delete")
    builder.adjust(1)
    return builder.as_markup()

def edit_options_keyboard(meeting_id: int, options: list) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования вариантов времени"""
    builder = InlineKeyboardBuilder()
    
    for opt in options:
        # Используем очень простой формат: del_{meeting_id}_{option_id}
        # Это исключает любые проблемы с спецсимволами
        callback_data = f"del_{meeting_id}_{opt['id']}"
        
        builder.button(
            text=f"❌ {opt['option_text']}",
            callback_data=callback_data
        )
    
    builder.button(text="➕ Добавить новый вариант", callback_data=f"add_{meeting_id}")
    builder.button(text="✅ Завершить редактирование", callback_data=f"finish_{meeting_id}")
    builder.adjust(1)
    return builder.as_markup()