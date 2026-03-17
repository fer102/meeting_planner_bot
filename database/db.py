import aiosqlite
import logging
from datetime import datetime, timedelta, timezone
from . import models

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "meeting_bot.db"):
        self.db_path = db_path

    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            for table_query in models.TABLES:
                await db.execute(table_query)
            await db.commit()
        logger.info("Таблицы в базе данных созданы/проверены")

    async def get_user(self, telegram_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_user(self, telegram_id: int, username: str = None, timezone: str = "UTC+3"):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO users (telegram_id, username, timezone) VALUES (?, ?, ?)",
                (telegram_id, username, timezone)
            )
            await db.commit()
            return cursor.lastrowid

    async def update_user_timezone(self, telegram_id: int, timezone: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET timezone = ? WHERE telegram_id = ?",
                (timezone, telegram_id)
            )
            await db.commit()

    async def create_meeting(self, creator_id: int, title: str, description: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO meetings (creator_id, title, description) VALUES (?, ?, ?)",
                (creator_id, title, description)
            )
            await db.commit()
            return cursor.lastrowid

    async def add_meeting_option(self, meeting_id: int, option_datetime: str, option_text: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO meeting_options (meeting_id, option_datetime, option_text) VALUES (?, ?, ?)",
                (meeting_id, option_datetime, option_text)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_meeting_options(self, meeting_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM meeting_options WHERE meeting_id = ? ORDER BY option_datetime",
                (meeting_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_meeting(self, meeting_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_meetings_by_user(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT DISTINCT m.* FROM meetings m 
                   LEFT JOIN participants p ON m.id = p.meeting_id 
                   WHERE m.creator_id = ? OR p.user_id = ?
                   ORDER BY m.created_at DESC""",
                (user_id, user_id)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_participant(self, meeting_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO participants (meeting_id, user_id) VALUES (?, ?)",
                (meeting_id, user_id)
            )
            await db.commit()

    async def get_user_votes(self, meeting_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT v.option_id FROM votes v
                   JOIN meeting_options mo ON v.option_id = mo.id
                   WHERE mo.meeting_id = ? AND v.user_id = ?""",
                (meeting_id, user_id)
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def vote(self, option_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO votes (option_id, user_id) VALUES (?, ?)",
                (option_id, user_id)
            )
            await db.commit()

    async def unvote(self, option_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM votes WHERE option_id = ? AND user_id = ?",
                (option_id, user_id)
            )
            await db.commit()

    async def get_vote_counts(self, meeting_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT mo.id, mo.option_text, COUNT(v.user_id) as votes_count,
                          GROUP_CONCAT(u.username) as voters
                   FROM meeting_options mo
                   LEFT JOIN votes v ON mo.id = v.option_id
                   LEFT JOIN users u ON v.user_id = u.id
                   WHERE mo.meeting_id = ?
                   GROUP BY mo.id
                   ORDER BY mo.option_datetime""",
                (meeting_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def set_finalized_option(self, meeting_id: int, option_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE meetings SET finalized_option_id = ? WHERE id = ?",
                (option_id, meeting_id)
            )
            await db.commit()
            logger.info(f"Для встречи {meeting_id} установлено финальное время {option_id}")

    async def delete_meeting(self, meeting_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            await db.commit()

    async def add_reminder(self, meeting_id: int, user_id: int, reminder_minutes: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO reminders (meeting_id, user_id, reminder_minutes, is_sent) VALUES (?, ?, ?, 0)",
                (meeting_id, user_id, reminder_minutes)
            )
            await db.commit()

    async def get_meeting_participants(self, meeting_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT u.* FROM users u
                   JOIN participants p ON u.id = p.user_id
                   WHERE p.meeting_id = ?
                   UNION
                   SELECT u.* FROM users u
                   JOIN meetings m ON u.id = m.creator_id
                   WHERE m.id = ?""",
                (meeting_id, meeting_id)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_reminders_to_send(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT r.id as reminder_id, r.user_id, r.reminder_minutes, 
                          m.id as meeting_id, m.title, mo.option_datetime
                   FROM reminders r
                   JOIN meetings m ON r.meeting_id = m.id
                   JOIN meeting_options mo ON m.finalized_option_id = mo.id
                   WHERE r.is_sent = 0"""
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_reminder_sent(self, reminder_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE reminders SET is_sent = 1 WHERE id = ?",
                (reminder_id,)
            )
            await db.commit()

    async def delete_past_meetings(self, user_id: int):
        """
        Удаляет прошедшие встречи ТОЛЬКО ДЛЯ УКАЗАННОГО ПОЛЬЗОВАТЕЛЯ (как создателя)
        Возвращает количество удаленных встреч
        """
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now(timezone.utc).isoformat()
            two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            
            # Получаем ID встреч для удаления (только где пользователь является создателем)
            cursor = await db.execute(
                """SELECT id FROM meetings
                   WHERE creator_id = ?
                   AND (
                       (finalized_option_id IS NOT NULL AND 
                        EXISTS(SELECT 1 FROM meeting_options 
                               WHERE id = finalized_option_id 
                               AND option_datetime < ?))
                       OR
                       (finalized_option_id IS NULL AND created_at < ?)
                   )""",
                (user_id, now, two_hours_ago)
            )
            rows = await cursor.fetchall()
            meeting_ids = [row[0] for row in rows]
            
            if meeting_ids:
                logger.info(f"Найдено {len(meeting_ids)} встреч для удаления у пользователя {user_id}: {meeting_ids}")
                
                for meeting_id in meeting_ids:
                    await db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
                
                await db.commit()
                return len(meeting_ids)
            else:
                logger.info(f"Нет встреч для удаления у пользователя {user_id}")
                return 0

    async def get_past_meetings_preview(self, user_id: int):
        """
        Возвращает список прошедших встреч пользователя для предпросмотра
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            now = datetime.now(timezone.utc).isoformat()
            two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            
            cursor = await db.execute(
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
                (user_id, now, two_hours_ago)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]