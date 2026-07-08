import asyncio
import os
import re
import time
import random
import string
import json
from collections import defaultdict, deque
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from yt_dlp import YoutubeDL

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "bot_database.db"

DEVELOPER_ID = "8597653867"
SUPPORT_ID = "8467593882"

DEFAULT_SUBSCRIBE_LINK = "tg://user?id=8597653867"
DEFAULT_BUTTON_TEXT = "تواصل مع المطور"
DEFAULT_BUTTON_STYLE = "primary"

SUPPORT_LINK = "tg://user?id=8467593882"
BTN_SUPPORT = "ابلاغ الدعم"
SUPPORT_BUTTON_STYLE = "destructive"

PROGRESS_START = "انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا"
PROGRESS_TEMPLATE = "انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا {percent}%"
ERROR_MESSAGE = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
FILE_NOT_FOUND = ERROR_MESSAGE

SUCCESS_MESSAGE = "يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك"
STARTUP_MESSAGE = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
QUEUE_FULL_MESSAGE = "سته عمليات داشتغل عليهم وبعدك تريد\nلعد شكد ملعوب بعرضك"

EMOJIS = ["🍕", "🌭", "🥪", "🥞", "🍣", "🍔"]
REACTION_EMOJIS = ["🥰", "😡", "😭", "🍓", "😘", "🤣", "🤗"]
REACTION_DELAYS = [3.6, 4.2, 4.8, 6.3, 2.4]

recent_reactions = deque(maxlen=4)
recent_delays = deque(maxlen=4)

def get_random_emoji() -> str:
    return random.choice(EMOJIS)

def get_unique_reaction() -> str:
    available = [e for e in REACTION_EMOJIS if e not in recent_reactions]
    chosen = random.choice(available if available else REACTION_EMOJIS)
    recent_reactions.append(chosen)
    return chosen

def get_unique_delay() -> float:
    available = [d for d in REACTION_DELAYS if d not in recent_delays]
    chosen = random.choice(available if available else REACTION_DELAYS)
    recent_delays.append(chosen)
    return chosen

async def trigger_delayed_reaction(bot_instance: Bot, chat_id: int, message_id: int):
    try:
        delay = get_unique_delay()
        reaction_emoji = get_unique_reaction()
        await asyncio.sleep(delay)
        await bot_instance.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[types.ReactionTypeEmoji(emoji=reaction_emoji)]
        )
    except Exception:
        pass

def get_buttons():
    kb = [
        [types.InlineKeyboardButton(text=DEFAULT_BUTTON_TEXT, url=DEFAULT_SUBSCRIBE_LINK, style=DEFAULT_BUTTON_STYLE)],
        [types.InlineKeyboardButton(text=BTN_SUPPORT, url=SUPPORT_LINK, style=SUPPORT_BUTTON_STYLE)]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

async def animate_text(message: types.Message, text: str, reply_markup: types.InlineKeyboardMarkup = None):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))

    lines = text.split('\n')
    parsed_lines = [line.split() for line in lines]
    
    line_indices = [0] * len(lines)
    line_toggles = [True] * len(lines)
    line_active = [False] * len(lines)
    
    if parsed_lines:
        line_active[0] = True

    first_chunk = " ".join(parsed_lines[0][0:3])
    line_indices[0] = 3
    line_toggles[0] = False
    
    sent_msg = await message.answer(first_chunk)
    await asyncio.sleep(0.3)

    chosen_emoji = get_random_emoji()

    while True:
        all_done = True
        for idx in range(len(lines)):
            if line_indices[idx] < len(parsed_lines[idx]):
                all_done = False
                break
        if all_done:
            break

        current_display_lines = []
        
        for idx in range(len(lines)):
            words = parsed_lines[idx]
            
            if line_active[idx] and line_indices[idx] < len(words):
                take = 3 if line_toggles[idx] else 2
                line_toggles[idx] = not line_toggles[idx]
                line_indices[idx] += take
                
                if idx + 1 < len(lines) and not line_active[idx + 1]:
                    line_active[idx + 1] = True

            current_line_text = " ".join(words[:line_indices[idx]])
            if current_line_text or idx < len(lines) - 1:
                current_display_lines.append(current_line_text)

        full_current_text = "\n".join(current_display_lines) + f"\n\n{chosen_emoji}"
        
        try:
            await sent_msg.edit_text(full_current_text)
            await asyncio.sleep(0.3)
        except Exception:
            pass

    try:
        final_text = text + f"\n\n{chosen_emoji}"
        markup = reply_markup if reply_markup else get_buttons()
        await sent_msg.edit_text(final_text, reply_markup=markup)
        asyncio.create_task(trigger_delayed_reaction(bot, sent_msg.chat.id, sent_msg.message_id))
    except Exception:
        pass

async def handle_response_1(message: types.Message):
    text = "اهلين وياك بوت ميديا تريد فيديو لو صورة دز\nرابطهن وتدلل"
    buttons = get_buttons()
    await animate_text(message, text, reply_markup=buttons)

async def handle_response_2(message: types.Message):
    text = "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك"
    buttons = get_buttons()
    await animate_text(message, text, reply_markup=buttons)

async def handle_response_3(message: types.Message):
    text = "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح"
    buttons = get_buttons()
    await animate_text(message, text, reply_markup=buttons)

async def handle_response_4(message: types.Message):
    text = "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
    buttons = get_buttons()
    await animate_text(message, text, reply_markup=buttons)

RESPONSE_HANDLERS = [
    handle_response_1,
    handle_response_2,
    handle_response_3,
    handle_response_4
]

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

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

user_queues = defaultdict(lambda: asyncio.Queue(maxsize=6))
user_workers = {}

def cleanup_stale_files():
    downloads_dir = 'downloads'
    if not os.path.exists(downloads_dir):
        return
    now = time.time()
    for filename in os.listdir(downloads_dir):
        file_path = os.path.join(downloads_dir, filename)
        if os.path.isfile(file_path):
            if now - os.path.getmtime(file_path) > 3600:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

def clean_filename_part(text: str) -> str:
    if not text:
        return ""
    
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9\s\-&]', '', text)
    cleaned = ' '.join(cleaned.split())
    
    result = []
    for char in cleaned:
        if char.isalpha():
            if char in 'ftanmjutFTANMJUT':
                result.append(char.upper())
            elif char in 'абиАБИ':
                result.append(char.upper())
            else:
                result.append(char.lower())
        else:
            result.append(char)
            
    return "".join(result).strip()

def generate_smart_filename(uploader: str) -> str:
    clean_uploader = clean_filename_part(uploader)
    if not clean_uploader:
        clean_uploader = "ANoNyMoUs"
        
    random_digits = "".join(random.choices(string.digits, k=9))
    return f"{clean_uploader} - {random_digits}"

def is_url(text: str) -> bool:
    if re.search(r'(t\.me|youtube\.com|youtu\.be)', text, re.IGNORECASE):
        return False
    regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return bool(re.match(regex, text))

async def process_download_task(message: types.Message, url_text: str):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))
    user_id = message.from_user.id
    
    cached_ids = await get_cached_file_ids(url_text)
    if cached_ids:
        try:
            chunks = [cached_ids[i:i + 8] for i in range(0, len(cached_ids), 8)]
            for chunk in chunks:
                media_group = []
                for idx, fid in enumerate(chunk):
                    if idx == 0:
                        caption_text = get_random_emoji().strip()
                        media_group.append(types.InputMediaDocument(media=fid, caption=caption_text))
                    else:
                        media_group.append(types.InputMediaDocument(media=fid))
                
                if len(media_group) == 1:
                    sent = await message.answer_document(media_group[0].media, caption=media_group[0].caption)
                    asyncio.create_task(trigger_delayed_reaction(bot, sent.chat.id, sent.message_id))
                else:
                    sent_group = await message.answer_media_group(media=media_group)
                    if sent_group:
                        asyncio.create_task(trigger_delayed_reaction(bot, sent_group[0].chat.id, sent_group[0].message_id))
                    
            sent_succ = await message.answer(SUCCESS_MESSAGE + f"\n\n{get_random_emoji()}", reply_markup=get_buttons())
            asyncio.create_task(trigger_delayed_reaction(bot, sent_succ.chat.id, sent_succ.message_id))
            return
        except Exception:
            pass

    cleanup_stale_files()
    progress_msg = await message.answer(PROGRESS_START)
    asyncio.create_task(trigger_delayed_reaction(bot, progress_msg.chat.id, progress_msg.message_id))
    last_reported_progress = 0
    downloaded_files = []
    
    loop = asyncio.get_running_loop()

    def ytdl_hook(d):
        nonlocal last_reported_progress
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                if percent >= 20 and percent >= last_reported_progress + 20:
                    last_reported_progress = (percent // 20) * 20
                    asyncio.run_coroutine_threadsafe(
                        progress_msg.edit_text(PROGRESS_TEMPLATE.format(percent=last_reported_progress)),
                        loop
                    )

    ydl_opts = {
        'format': 'best',
        'progress_hooks': [ytdl_hook],
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False
    }
    
    try:
        ydl = YoutubeDL(ydl_opts)
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url_text, download=False))
        
        uploader = info.get('uploader') or info.get('channel') or "ANoNyMoUs"
        
        entries = []
        if 'entries' in info and info['entries']:
            entries = [e for e in info['entries'] if e]
        else:
            entries = [info]
            
        for entry in entries:
            custom_name = generate_smart_filename(uploader)
            entry_opts = {
                'format': 'best',
                'outtmpl': f'downloads/{custom_name}.%(ext)s',
                'quiet': True,
                'no_warnings': True
            }
            entry_info = await loop.run_in_executor(None, lambda: YoutubeDL(entry_opts).extract_info(entry.get('webpage_url') or url_text, download=True))
            filename = YoutubeDL(entry_opts).prepare_filename(entry_info)
            if os.path.exists(filename):
                downloaded_files.append(filename)

        await progress_msg.delete()
        
        if downloaded_files:
            chunks = [downloaded_files[i:i + 8] for i in range(0, len(downloaded_files), 8)]
            uploaded_file_ids = []
            
            for chunk in chunks:
                media_group = []
                for idx, filepath in enumerate(chunk):
                    file_input = types.FSInputFile(filepath)
                    if idx == 0:
                        caption_text = get_random_emoji().strip()
                        media_group.append(types.InputMediaDocument(media=file_input, caption=caption_text))
                    else:
                        media_group.append(types.InputMediaDocument(media=file_input))
                
                if len(media_group) == 1:
                    sent_doc = await message.answer_document(media_group[0].media, caption=media_group[0].caption)
                    uploaded_file_ids.append(sent_doc.document.file_id)
                    asyncio.create_task(trigger_delayed_reaction(bot, sent_doc.chat.id, sent_doc.message_id))
                else:
                    sent_group = await message.answer_media_group(media=media_group)
                    if sent_group:
                        asyncio.create_task(trigger_delayed_reaction(bot, sent_group[0].chat.id, sent_group[0].message_id))
                    for sent_msg in sent_group:
                        if sent_msg.document:
                            uploaded_file_ids.append(sent_msg.document.file_id)
            
            if uploaded_file_ids:
                await save_cached_file_ids(url_text, uploaded_file_ids)
                
            sent_final = await message.answer(SUCCESS_MESSAGE + f"\n\n{get_random_emoji()}", reply_markup=get_buttons())
            asyncio.create_task(trigger_delayed_reaction(bot, sent_final.chat.id, sent_final.message_id))
        else:
            sent_err = await message.answer(FILE_NOT_FOUND + f"\n\n{get_random_emoji()}")
            asyncio.create_task(trigger_delayed_reaction(bot, sent_err.chat.id, sent_err.message_id))
            
    except Exception:
        try:
            await progress_msg.edit_text(ERROR_MESSAGE + f"\n\n{get_random_emoji()}")
        except Exception:
            pass
    finally:
        for filepath in downloaded_files:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

async def user_queue_worker(user_id: int):
    queue = user_queues[user_id]
    while True:
        message, url_text = await queue.get()
        try:
            await process_download_task(message, url_text)
        except Exception:
            pass
        finally:
            queue.task_done()

@dp.message(F.text)
async def handle_message(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    if is_url(text):
        queue = user_queues[user_id]
        if queue.full():
            sent_q = await message.answer(QUEUE_FULL_MESSAGE + f"\n\n{get_random_emoji()}")
            asyncio.create_task(trigger_delayed_reaction(bot, sent_q.chat.id, sent_q.message_id))
            return
            
        await queue.put((message, text))
        
        if user_id not in user_workers or user_workers[user_id].done():
            user_workers[user_id] = asyncio.create_task(user_queue_worker(user_id))
    else:
        current_index = await get_user_step(user_id)
        
        handler_func = RESPONSE_HANDLERS[current_index]
        
        next_index = (current_index + 1) % len(RESPONSE_HANDLERS)
        await update_user_step(user_id, next_index)
        
        await handler_func(message)

async def on_startup():
    for admin_id in [DEVELOPER_ID, SUPPORT_ID]:
        try:
            await bot.send_message(chat_id=admin_id, text=STARTUP_MESSAGE)
        except Exception:
            pass

async def main():
    await init_db()
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
