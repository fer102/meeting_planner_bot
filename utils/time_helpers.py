from datetime import datetime, timedelta, timezone
import re
from typing import List

TIMEZONES = {
    "UTC+2": "Калининград",
    "UTC+3": "Москва",
    "UTC+4": "Самара",
    "UTC+5": "Екатеринбург",
    "UTC+6": "Омск",
    "UTC+7": "Красноярск",
    "UTC+8": "Иркутск",
    "UTC+9": "Якутск",
    "UTC+10": "Владивосток",
    "UTC+11": "Магадан",
    "UTC+12": "Камчатка"
}

def get_timezone_display(utc_offset: str) -> str:
    city = TIMEZONES.get(utc_offset, "")
    return f"{utc_offset} ({city})" if city else utc_offset

def parse_timezone_from_display(display_text: str) -> str:
    match = re.match(r"(UTC[+-]\d+)", display_text)
    return match.group(1) if match else "UTC+3"

def utc_now() -> datetime:
    """Возвращает текущее время в UTC"""
    return datetime.now(timezone.utc)

def get_offset_hours(timezone_str: str) -> int:
    """Получить смещение в часах из строки типа 'UTC+3'"""
    match = re.search(r"UTC([+-])(\d+)", timezone_str)
    if match:
        sign = match.group(1)
        hours = int(match.group(2))
        return hours if sign == '+' else -hours
    return 0

def utc_to_local_time(utc_dt: datetime, timezone_str: str) -> datetime:
    """Конвертирует UTC время в локальное время пользователя"""
    offset = get_offset_hours(timezone_str)
    local_dt = utc_dt + timedelta(hours=offset)
    return local_dt.replace(tzinfo=None)

def local_to_utc_time(local_dt: datetime, timezone_str: str) -> datetime:
    """Конвертирует локальное время пользователя в UTC"""
    offset = get_offset_hours(timezone_str)
    utc_dt = local_dt - timedelta(hours=offset)
    return utc_dt.replace(tzinfo=timezone.utc)

def get_available_dates(user_timezone: str = None) -> List[datetime]:
    """
    Возвращает список доступных дат в UTC: сегодня и следующие 6 дней
    Если передан часовой пояс, фильтрует сегодняшнюю дату, если на неё нет доступного времени
    """
    now_utc = utc_now()
    dates = []
    
    for i in range(7):
        date = now_utc + timedelta(days=i)
        date = datetime(date.year, date.month, date.day, tzinfo=timezone.utc)
        
        # Если указан часовой пояс, проверяем, есть ли доступное время для этой даты
        if user_timezone and i == 0:  # Только для сегодняшней даты
            available_times = get_available_times_for_date(date, user_timezone)
            if available_times:  # Если есть доступное время, добавляем дату
                dates.append(date)
        else:
            dates.append(date)
    
    return dates

def get_available_times_for_date(date: datetime, user_timezone: str) -> List[str]:
    """
    Возвращает доступное время для даты (10:00-17:00 по LOCAL времени пользователя)
    date - дата в UTC
    user_timezone - часовой пояс пользователя
    """
    now_utc = utc_now()
    
    # Конвертируем текущее время в локальное время пользователя
    now_local = utc_to_local_time(now_utc, user_timezone)
    
    # Конвертируем выбранную дату в локальное время пользователя
    date_local = utc_to_local_time(date, user_timezone)
    
    times = []
    
    for hour in range(10, 18):  # 10:00 до 17:00 по LOCAL времени
        # Создаем локальное время для этого часа
        local_dt = datetime(date_local.year, date_local.month, date_local.day, 
                           hour, 0, 0, 0)
        
        # Для сегодняшнего дня показываем только будущее время
        if date_local.date() == now_local.date():
            if local_dt > now_local:
                times.append(f"{hour:02d}:00")
        else:
            times.append(f"{hour:02d}:00")
    
    return times

def format_datetime_for_user(dt_str: str, user_timezone: str) -> str:
    """Конвертирует datetime из UTC в часовой пояс пользователя и форматирует"""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
    
    dt_local = utc_to_local_time(dt, user_timezone)
    return dt_local.strftime("%d.%m.%Y %H:%M")

def utc_to_local(utc_dt_str: str, user_timezone: str) -> str:
    return format_datetime_for_user(utc_dt_str, user_timezone)

def local_to_utc(local_dt_str: str, user_timezone: str) -> str:
    """Конвертирует локальное время в UTC для хранения"""
    dt = datetime.strptime(local_dt_str, "%d.%m.%Y %H:%M")
    dt_utc = local_to_utc_time(dt, user_timezone)
    return dt_utc.isoformat()