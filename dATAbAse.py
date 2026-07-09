import os
import json
import aiosqlite

DB_PATH = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                step_counter INTEGER DEFAULT 0
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS url_cache (
                url TEXT PRIMARY KEY,
                file_ids TEXT
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER PRIMARY KEY,
                mute_notifications INTEGER DEFAULT 0,
                force_sub_link TEXT DEFAULT '',
                admin_state TEXT DEFAULT 'none'
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_state (
                key TEXT PRIMARY KEY,
                val INTEGER DEFAULT 0
            );
        """)
        await db.commit()

async def get_user_step(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT step_counter FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                await db.execute("INSERT INTO users (user_id, step_counter) VALUES (?, 0)", (user_id,))
                await db.commit()
                return 0
            return row[0]

async def update_user_step(user_id: int, new_step: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET step_counter = ? WHERE user_id = ?", (new_step, user_id))
        await db.commit()

async def get_cached_file_ids(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT file_ids FROM url_cache WHERE url = ?", (url,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None

async def save_cached_file_ids(url: str, file_ids: list):
    async with aiosqlite.connect(DB_PATH) as db:
        json_data = json.dumps(file_ids)
        await db.execute(
            "INSERT INTO url_cache (url, file_ids) VALUES (?, ?) ON CONFLICT(url) DO UPDATE SET file_ids = ?",
            (url, json_data, json_data)
        )
        await db.commit()

async def get_notification_status(chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT mute_notifications FROM settings WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return 0
            return row[0]

async def set_notification_status(chat_id: int, status: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (chat_id, mute_notifications) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET mute_notifications = ?",
            (chat_id, status, status)
        )
        await db.commit()

async def get_force_sub_link() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT force_sub_link FROM settings WHERE chat_id = 0") as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return ""

async def set_force_sub_link(link: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (chat_id, force_sub_link) VALUES (0, ?) ON CONFLICT(chat_id) DO UPDATE SET force_sub_link = ?",
            (link, link)
        )
        await db.commit()

async def get_admin_state(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT admin_state FROM settings WHERE chat_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return "none"

async def set_admin_state(user_id: int, state: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (chat_id, admin_state) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET admin_state = ?",
            (user_id, state, state)
        )
        await db.commit()

async def get_next_emoji_index() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT val FROM global_state WHERE key = 'emoji_idx'") as cursor:
            row = await cursor.fetchone()
            if row:
                current = row[0]
                next_idx = (current + 1) % 7
                await db.execute("UPDATE global_state WHERE key = 'emoji_idx'", (next_idx,))
                await db.commit()
                return current
            else:
                await db.execute("INSERT INTO global_state (key, val) VALUES ('emoji_idx', 1)")
                await db.commit()
                return 0