import os
import aiosqlite

DB_PATH = "bot_cache.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_cache (
                url_query TEXT PRIMARY KEY,
                file_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS yt_cache (
                video_id TEXT PRIMARY KEY,
                file_id TEXT
            )
        """)
        await db.commit()

async def get_cached_file(url_or_query):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT file_id FROM file_cache WHERE url_query = ?", (url_or_query,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_file_cache(url_or_query, file_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO file_cache (url_query, file_id) VALUES (?, ?)", (url_or_query, file_id))
        await db.commit()

async def get_yt_cache(video_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT file_id FROM yt_cache WHERE video_id = ?", (video_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_yt_cache(video_id, file_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO yt_cache (video_id, file_id) VALUES (?, ?)", (video_id, file_id))
        await db.commit()

def clear_system_file(file_path):
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass
