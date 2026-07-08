import os
import asyncpg
import json

DATABASE_URL = os.getenv("DATABASE_URL")

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(dsn=DATABASE_URL)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                step_counter INT DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS url_cache (
                url TEXT PRIMARY KEY,
                file_ids TEXT
            );
        """)

async def get_user_step(user_id: int) -> int:
    global pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT step_counter FROM users WHERE user_id = $1", user_id)
        if row is None:
            await conn.execute("INSERT INTO users (user_id, step_counter) VALUES ($1, 0)", user_id)
            return 0
        return row['step_counter']

async def update_user_step(user_id: int, new_step: int):
    global pool
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET step_counter = $1 WHERE user_id = $2", new_step, user_id)

async def get_cached_file_ids(url: str):
    global pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT file_ids FROM url_cache WHERE url = $1", url)
        if row and row['file_ids']:
            return json.loads(row['file_ids'])
        return None

async def save_cached_file_ids(url: str, file_ids: list):
    global pool
    async with pool.acquire() as conn:
        json_data = json.dumps(file_ids)
        await conn.execute(
            "INSERT INTO url_cache (url, file_ids) VALUES ($1, $2) ON CONFLICT (url) DO UPDATE SET file_ids = $2",
            url, json_data
        )
