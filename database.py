import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "assistant.db")


class Database:
    def __init__(self):
        self.db_path = DB_PATH

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def init(self):
        conn = self.get_conn()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                created_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                created_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                done INTEGER DEFAULT 0,
                priority TEXT DEFAULT 'medium',
                deadline TEXT,
                created_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                key TEXT,
                value TEXT,
                updated_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                remind_at TEXT,
                sent INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        conn.commit()
        conn.close()

    def save_user(self, user_id: int, name: str):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def get_all_users(self):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id, name FROM users")
        rows = c.fetchall()
        conn.close()
        return rows

    # ── MESSAGES ──────────────────────────────────────────────

    def add_message(self, user_id: int, role: str, content: str):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def get_history(self, user_id: int, limit: int = 20):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        rows = c.fetchall()
        conn.close()
        return list(reversed(rows))

    def clear_history(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # ── NOTES ─────────────────────────────────────────────────

    def add_note(self, user_id: int, content: str):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def get_notes(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        rows = c.fetchall()
        conn.close()
        return rows

    def delete_note(self, user_id: int, note_id: int) -> bool:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    # ── TASKS ─────────────────────────────────────────────────

    def add_task(self, user_id: int, content: str, priority: str = "medium", deadline: str = None):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO tasks (user_id, content, done, priority, deadline, created_at) VALUES (?, ?, 0, ?, ?, ?)",
            (user_id, content, priority, deadline, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def get_tasks(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT id, content, done, priority, deadline, created_at
               FROM tasks WHERE user_id = ?
               ORDER BY done ASC,
                        CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                        id DESC""",
            (user_id,)
        )
        rows = c.fetchall()
        conn.close()
        return rows

    def complete_task(self, user_id: int, task_id: int) -> bool:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET done = 1 WHERE id = ? AND user_id = ?",
            (task_id, user_id)
        )
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def delete_task(self, user_id: int, task_id: int) -> bool:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    # ── MEMORY ────────────────────────────────────────────────

    def set_memory(self, user_id: int, key: str, value: str):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM user_memory WHERE user_id = ? AND key = ?", (user_id, key))
        existing = c.fetchone()
        if existing:
            c.execute(
                "UPDATE user_memory SET value = ?, updated_at = ? WHERE user_id = ? AND key = ?",
                (value, datetime.now().isoformat(), user_id, key)
            )
        else:
            c.execute(
                "INSERT INTO user_memory (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, key, value, datetime.now().isoformat())
            )
        conn.commit()
        conn.close()

    def get_memory(self, user_id: int) -> dict:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT key, value FROM user_memory WHERE user_id = ?", (user_id,))
        rows = c.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    def delete_memory_key(self, user_id: int, key: str) -> bool:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM user_memory WHERE user_id = ? AND key = ?", (user_id, key))
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    # ── REMINDERS ─────────────────────────────────────────────

    def add_reminder(self, user_id: int, text: str, remind_at: str):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO reminders (user_id, text, remind_at, sent, created_at) VALUES (?, ?, ?, 0, ?)",
            (user_id, text, remind_at, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def get_pending_reminders(self):
        conn = self.get_conn()
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute(
            "SELECT id, user_id, text FROM reminders WHERE sent = 0 AND remind_at <= ?",
            (now,)
        )
        rows = c.fetchall()
        conn.close()
        return rows

    def mark_reminder_sent(self, reminder_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
        conn.commit()
        conn.close()

    def get_user_reminders(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, text, remind_at FROM reminders WHERE user_id = ? AND sent = 0 ORDER BY remind_at ASC",
            (user_id,)
        )
        rows = c.fetchall()
        conn.close()
        return rows
