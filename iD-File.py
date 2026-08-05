import os
import sqlite3
from aiogram import Router, F, Bot, types

DB_PATH = os.environ.get("DATABASE_PATH", "bot.db")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS file_store (
    file_key TEXT PRIMARY KEY,
    file_id TEXT,
    file_type TEXT
)
""")
conn.commit()

def save_file_id(key: str, file_id: str, file_type: str = "document"):
    cursor.execute("INSERT OR REPLACE INTO file_store (file_key, file_id, file_type) VALUES (?, ?, ?)", (key, file_id, file_type))
    conn.commit()

def get_file_id(key: str):
    cursor.execute("SELECT file_id, file_type FROM file_store WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row:
        return {"file_id": row[0], "file_type": row[1]}
    return None

file_router = Router()

@file_router.message(F.chat.type == "private", F.reply_to_message, F.text == "ايدي الملف")
async def get_replied_file_id_handler(message: types.Message):
    reply = message.reply_to_message
    file_id = None
    file_type = None

    if reply.document:
        file_id = reply.document.file_id
        file_type = "document"
    elif reply.video:
        file_id = reply.video.file_id
        file_type = "video"
    elif reply.photo:
        file_id = reply.photo[-1].file_id
        file_type = "photo"
    elif reply.audio:
        file_id = reply.audio.file_id
        file_type = "audio"
    elif reply.voice:
        file_id = reply.voice.file_id
        file_type = "voice"
    elif reply.sticker:
        file_id = reply.sticker.file_id
        file_type = "sticker"

    if file_id:
        text = f"¹# - File ID:\n`{file_id}`\nType: {file_type}"
        await message.reply(text, parse_mode="Markdown")
