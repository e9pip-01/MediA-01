import os
import re
import asyncio
import random
import sqlite3
import shutil
import mimetypes
import yt_dlp
import importlib
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from yoUGro import router as group_router, get_user_role, get_group_buttons

id_file_module = importlib.import_module("iD-File")
file_router = id_file_module.file_router

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DATABASE_PATH", "bot.db")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    val INTEGER
)
""")
conn.commit()

def get_state(key, default=0):
    cursor.execute("SELECT val FROM state WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO state (key, val) VALUES (?, ?)", (key, default))
    conn.commit()
    return default

def set_state(key, val):
    cursor.execute("INSERT OR REPLACE INTO state (key, val) VALUES (?, ?)", (key, val))
    conn.commit()

EMOJIS = ["😭", "😡", "🌭", "🤣", "🥰", "🍓", "😘", "😁"]
DELAYS = [2.4, 4.2, 4.8, 3.6, 3.2, 2.3]

def get_next_emoji():
    idx = get_state("emoji_idx", 0)
    emoji = EMOJIS[idx]
    next_idx = (idx + 1) % len(EMOJIS)
    set_state("emoji_idx", next_idx)
    return emoji

def get_next_delay():
    idx = get_state("delay_idx", 0)
    delay = DELAYS[idx]
    next_idx = (idx + 1) % len(DELAYS)
    set_state("delay_idx", next_idx)
    return delay

def get_next_button():
    btn_cycle = get_state("btn_cycle", 0)
    color_cycle = get_state("color_cycle", 0)
    style = "danger" if color_cycle % 2 == 0 else "primary"
    
    bot_info_idx = btn_cycle % 4
    if bot_info_idx == 0 or bot_info_idx == 2:
        btn = InlineKeyboardButton(text="رقوش", url="tg://openmessage?user_id=8436425159", style=style)
    elif bot_info_idx == 1:
        btn = InlineKeyboardButton(text="المطور", url="tg://openmessage?user_id=8436425159", style=style)
    else:
        btn = InlineKeyboardButton(text="مشاركة", url="https://t.me/share/url?url=@" + bot_username, style=style)
        
    set_state("btn_cycle", btn_cycle + 1)
    set_state("color_cycle", color_cycle + 1)
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])

def transform_case(text):
    allowed_upper = set("ATFGNMUJLАБИ")
    res = []
    for char in text:
        if char.upper() in allowed_upper:
            res.append(char.upper())
        else:
            res.append(char.lower())
    return "".join(res)

def clean_name(uploader, title):
    uploader_clean = re.sub(r'[^a-zA-Zа-яА-Я0-9_\s]', '', uploader).strip()
    title_clean = re.sub(r'[^a-zA-Zа-яА-Я0-9&\-\s]', '', title).strip()
    return f"{transform_case(uploader_clean)} - {transform_case(title_clean)}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
bot_username = ""

async def trigger_reaction_and_delay(chat_id, message_id):
    delay = get_next_delay()
    await asyncio.sleep(delay)
    emoji = get_next_emoji()
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[types.ReactionTypeEmoji(emoji=emoji)]
        )
    except Exception:
        pass

MARKDOWN_LINK_REGEX = r'\[([^\]]+)\]\((https?://[^\s)]+)\)'
URL_REGEX = r'https?://[^\s]+'

def extract_url(text):
    if not text:
        return None
    md_match = re.search(MARKDOWN_LINK_REGEX, text)
    if md_match:
        return md_match.group(2)
    
    url_match = re.search(URL_REGEX, text)
    if url_match:
        return url_match.group(0)
        
    return None

def is_ignored_link(text):
    if not text:
        return False
    url = extract_url(text)
    if not url:
        return True
    ignored_patterns = [
        r'(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)',
        r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)'
    ]
    for pattern in ignored_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False

@dp.message(F.text.func(lambda t: extract_url(t) is not None))
async def handle_download(message: types.Message):
    if is_ignored_link(message.text):
        return
        
    if message.chat.type in ["group", "supergroup"]:
        role = await get_user_role(bot, message.chat.id, message.from_user.id)
        if role not in ["مالك", "ادمن", "مميز"]:
            return

    asyncio.create_task(process_download(message))

async def process_download(message: types.Message):
    url = extract_url(message.text)
    if not url:
        return
        
    asyncio.create_task(trigger_reaction_and_delay(message.chat.id, message.message_id))
    
    folder = f"dl_{message.message_id}_{random.randint(1000, 9999)}"
    os.makedirs(folder, exist_ok=True)
    
    ydl_opts_single = {'format': 'best[has_video][has_audio]/best', 'outtmpl': f'{folder}/single.%(ext)s', 'quiet': True, 'no_warnings': True}
    ydl_opts_split = {'format': 'bestvideo+bestaudio/best', 'outtmpl': f'{folder}/split.%(ext)s', 'quiet': True, 'no_warnings': True}
    
    file_path = None
    custom_name = "media"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_single) as ydl:
            info = ydl.extract_info(url, download=True)
            uploader = info.get('uploader') or info.get('channel') or 'Media'
            title = info.get('title') or 'Video'
            custom_name = clean_name(uploader, title)
            for f in os.listdir(folder):
                file_path = os.path.join(folder, f)
                break
    except Exception:
        try:
            with yt_dlp.YoutubeDL(ydl_opts_split) as ydl:
                info = ydl.extract_info(url, download=True)
                uploader = info.get('uploader') or info.get('channel') or 'Media'
                title = info.get('title') or 'Video'
                custom_name = clean_name(uploader, title)
                for f in os.listdir(folder):
                    file_path = os.path.join(folder, f)
                    break
        except Exception:
            file_path = None

    if not file_path or not os.path.exists(file_path):
        shutil.rmtree(folder, ignore_errors=True)
        return

    mime_type, _ = mimetypes.guess_type(file_path)
    ext = mimetypes.guess_extension(mime_type) if mime_type else os.path.splitext(file_path)[1]
    if not ext:
        ext = ".mp4"
        
    final_file = os.path.join(folder, f"{custom_name}{ext}")
    os.rename(file_path, final_file)
    
    try:
        await message.reply_video(video=FSInputFile(final_file), has_spoiler=True)
    except Exception:
        try:
            await message.reply_document(document=FSInputFile(final_file))
        except Exception:
            pass
            
    shutil.rmtree(folder, ignore_errors=True)

@dp.message(F.chat.type == "private")
async def private_chat_handler(message: types.Message):
    if is_ignored_link(message.text) or extract_url(message.text or ""):
        return
        
    asyncio.create_task(trigger_reaction_and_delay(message.chat.id, message.message_id))
    
    msg_cycle = get_state("msg_cycle", 0)
    text = "اهلين وياك بوت ميديا تريد اشتغل\nدز رابط المنشور وتلقاه فورا" if msg_cycle % 2 == 0 else "مو ناوي\nتدلعني مثل البوتات ترى ازعل منك اصيح المولاي"
    set_state("msg_cycle", msg_cycle + 1)
    
    sent_msg = await message.reply(text, reply_markup=get_next_button())
    asyncio.create_task(trigger_reaction_and_delay(sent_msg.chat.id, sent_msg.message_id))

@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: t and "بوت" in t))
async def group_chat_handler(message: types.Message):
    if is_ignored_link(message.text) or extract_url(message.text or ""):
        return

    role = await get_user_role(bot, message.chat.id, message.from_user.id)
    if role not in ["مالك", "ادمن", "مميز"]:
        return

    asyncio.create_task(trigger_reaction_and_delay(message.chat.id, message.message_id))
    
    msg_cycle = get_state("msg_cycle", 0)
    text = "اهلين وياك بوت ميديا تريد اشتغل\nدز رابط المنشور وتلقاه فورا" if msg_cycle % 2 == 0 else "مو ناوي\nتدلعني مثل البوتات ترى ازعل منك اصيح المولاي"
    set_state("msg_cycle", msg_cycle + 1)
    
    sent_msg = await message.reply(text, reply_markup=get_group_buttons(message.from_user.id))
    asyncio.create_task(trigger_reaction_and_delay(sent_msg.chat.id, sent_msg.message_id))

async def main():
    global bot_username
    me = await bot.get_me()
    bot_username = me.username
    dp.include_router(group_router)
    dp.include_router(file_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
