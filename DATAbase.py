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
