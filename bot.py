import os
import re
import asyncio
import random
import time
import aiosqlite
import mimetypes
import urllib.parse
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ChatMemberUpdated, CallbackQuery, InputMediaDocument, ReactionTypeEmoji
from aiogram.filters import ChatMemberUpdatedFilter
import yt_dlp
from googletrans import Translator  # تغيير مكتبة الترجمة هنا

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

download_queue = asyncio.Queue()
user_task_counts = {}
counter_lock = asyncio.Lock()

welcome_state = 0
active_emoji_tasks = {}
admin_states = {}

PRIMARY_ADMINS = [8597653867, 8467593882]

DEFAULT_SUBSCRIBE_LINK = "tg://user?id=8597653867"
DEFAULT_BUTTON_TEXT = "رب العالمين"
DEFAULT_BUTTON_STYLE = "primary"

REACTIONS_POOL = ["🥰", "😡", "😘", "🍓", "🤣", "🤗", "😭"]
last_user_reaction = {}
last_bot_reaction = {}

ANY_URL_REGEX = re.compile(r'(https?://[^\s]+)')

STRICT_USERNAME_REGEX = re.compile(r'^@?(?=[a-zA-Z])[a-zA-Z0-9](?:[a-zA-Z0-9_]*[a-zA-Z0-9])?$')
CHANNEL_USER_REGEX = re.compile(r'^(https?://)?(www\.)?(t\.me/)?(joinchat/)?(⚡️)?[a-zA-Z][a-zA-Z0-9]{3,30}(?<!_)(?<![0-9])_?[a-zA-Z0-9]+(?<!_)$|^@[a-zA-Z][a-zA-Z0-9_]{3,30}(?<!_)$')

EMOJI_SEQUENCE = ["🫦", "👅", "👄", "🌭", "🍔", "🍕"]
emoji_index = 0
emoji_lock = asyncio.Lock()

SUCCESS_RESPONSES = [
    "الميديا الردتها كدامك مولاي\nيدلل تاج راسي",
    "يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل العيرك\nذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك واكلك نيكني يبعد كل طموح شكني بعيرك\nوضرطني العافيه ترى فدوه الك اروح"
]

class ProgressTracker:
    def __init__(self, bot: Bot, chat_id: int, message_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_percent = 0

    async def update(self, current: int, total: int):
        if not total:
            return
        percent = int((current / total) * 100)
        if (percent - self.last_percent >= 20) or (percent == 100 and self.last_percent != 100):
            self.last_percent = percent
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    text=f"انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا\n\nجاري التحميل: {percent}%"
                )
            except Exception:
                pass

def clean_and_format_text(text: str) -> str:
    if not text:
        return ""
    if text.strip().startswith("/"):
        return text
    lowered = text.lower()
    eng_to_upper = ['a', 't', 'n', 'g', 'f', 'u', 'j', 'm']
    rus_to_upper = ['а', 'и', 'б']
    chars = list(lowered)
    for idx, char in enumerate(chars):
        if char in eng_to_upper or char in rus_to_upper:
            chars[idx] = char.upper()
    result_text = "".join(chars)
    filtered = re.sub(r'[^a-zA-Z0-9а-яА-ЯёЁ\u0600-\u06FF\s\-]', '', result_text)
    filtered = re.sub(r'\s+', ' ', filtered).strip()
    return filtered

def clean_and_format_translation(text: str, target_lang: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    eng_to_upper = ['a', 't', 'n', 'g', 'f', 'u', 'j', 'm']
    rus_to_upper = ['а', 'и', 'б']
    chars = list(lowered)
    for idx, char in enumerate(chars):
        if target_lang == "en" and char in eng_to_upper:
            chars[idx] = char.upper()
        elif target_lang == "ru" and char in rus_to_upper:
            chars[idx] = char.upper()
    result_text = "".join(chars)
    filtered = re.sub(r'[^a-zA-Z0-9а-яА-ЯёЁ\u0600-\u06FF\s\-\&\:\@\/]', '', result_text)
    filtered = re.sub(r'\s+', ' ', filtered).strip()
    return filtered

async def init_db():
    async with aiosqlite.connect("bot_data.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users_log (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS permissions_cache (
                chat_id INTEGER,
                user_id INTEGER,
                is_admin INTEGER,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS media_cache (
                media_key TEXT PRIMARY KEY,
                file_id TEXT,
                media_type TEXT,
                title TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_notifications (
                chat_id INTEGER PRIMARY KEY,
                status TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_protection (
                chat_id INTEGER PRIMARY KEY,
                status TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS translation_settings (
                user_id INTEGER PRIMARY KEY,
                lang TEXT,
                mode INTEGER
            )
        """)
        await db.commit()

def is_all_admins(user_id: int) -> bool:
    return user_id in PRIMARY_ADMINS

async def get_setting(key: str, default: str) -> str:
    async with aiosqlite.connect("bot_data.db") as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row: return row[0]
            return default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect("bot_data.db") as db:
        await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def is_content_protected(chat_id: int) -> bool:
    async with aiosqlite.connect("bot_data.db") as db:
        async with db.execute("SELECT status FROM chat_protection WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row: return row[0] == "locked"
            return False

def extract_channel_chat_id(url: str):
    clean = url.strip()
    if "t.me/" in clean:
        parts = clean.split("t.me/")
        if len(parts) > 1:
            username = parts[1].split('?')[0]
            if not username.startswith("@") and not username.startswith("joinchat/"):
                return f"@{username}"
    if clean.startswith("@"):
        return clean
    return None

async def is_custom_link_set() -> bool:
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    return sub_link != DEFAULT_SUBSCRIBE_LINK

async def check_force_subscription(user_id: int) -> bool:
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    if sub_link == DEFAULT_SUBSCRIBE_LINK: return True
    target_chat = extract_channel_chat_id(sub_link)
    if not target_chat: return True
    try:
        member = await bot.get_chat_member(chat_id=target_chat, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return True

async def get_sub_keyboard() -> InlineKeyboardMarkup:
    btn_text = await get_setting("btn_text", DEFAULT_BUTTON_TEXT)
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=sub_link)]])

async def get_force_sub_keyboard() -> InlineKeyboardMarkup:
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اشترك بالقناة", url=sub_link)]])

def get_clean_url(input_str: str) -> str:
    input_str = input_str.strip()
    if input_str.startswith("@"): return f"https://t.me/{input_str[1:]}"
    if input_str.startswith("http://") or input_str.startswith("https://"): return input_str
    if input_str.startswith("t.me/"): return f"https://{input_str}"
    return f"https://t.me/{input_str}"

def get_smart_reaction(last_reaction_dict, key: int) -> str:
    last = last_reaction_dict.get(key)
    available = [r for r in REACTIONS_POOL if r != last]
    chosen = random.choice(available)
    last_reaction_dict[key] = chosen
    return chosen

async def delayed_react(chat_id: int, message_id: int, emoji: str, delay: float = None):
    if delay is None: delay = random.choice([1.0, 1.8, 2.5])
    await asyncio.sleep(delay)
    try:
        await bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=[{"type": "emoji", "emoji": emoji}], is_big=False)
    except Exception:
        pass

async def is_user_admin_or_owner(chat_id: int, user_id: int, force_update: bool = False) -> bool:
    if is_all_admins(user_id): return True
    if not force_update:
        async with aiosqlite.connect("bot_data.db") as db:
            async with db.execute("SELECT is_admin FROM permissions_cache WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)) as cursor:
                row = await cursor.fetchone()
                if row: return bool(row[0])
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        res = member.status in ["administrator", "creator"]
    except Exception:
        res = False
    async with aiosqlite.connect("bot_data.db") as db:
        await db.execute("INSERT OR REPLACE INTO permissions_cache (chat_id, user_id, is_admin) VALUES (?, ?, ?)", (chat_id, user_id, int(res)))
        await db.commit()
    return res

async def is_user_owner(chat_id: int, user_id: int) -> bool:
    if is_all_admins(user_id): return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status == "creator"
    except Exception:
        return False

@dp.chat_member()
async def on_chat_member_updated(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user_id = event.new_chat_member.user.id
    async with aiosqlite.connect("bot_data.db") as db:
        await db.execute("DELETE FROM permissions_cache WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await db.commit()

def spawn_emoji_task(bot_message: Message, custom_emoji: str = None, reply_markup=None, trigger_by_user_id: int = 0):
    async def trigger():
        global emoji_index
        if not bot_message: return
        chat_id = bot_message.chat.id
        try:
            protect = await is_content_protected(chat_id)
            if custom_emoji:
                rep_msg = await bot_message.reply(custom_emoji, reply_markup=reply_markup, protect_content=protect)
            else:
                async with emoji_lock:
                    selected = EMOJI_SEQUENCE[emoji_index]
                    emoji_index = (emoji_index + 1) % len(EMOJI_SEQUENCE)
                rep_msg = await bot_message.reply(selected, reply_markup=reply_markup, protect_content=protect)
            if rep_msg:
                bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                asyncio.create_task(delayed_react(chat_id, rep_msg.message_id, bot_emoji))
                bot_reply_emoji = get_smart_reaction(last_user_reaction, chat_id)
                asyncio.create_task(delayed_react(chat_id, rep_msg.message_id, bot_reply_emoji))
            if bot_message.message_id in active_emoji_tasks:
                active_emoji_tasks[bot_message.message_id] = rep_msg
        except Exception:
            pass
    asyncio.create_task(trigger())

def analyze_media(info_dict: dict) -> tuple[str, str]:
    if not info_dict:
        return "unknown", ""
    ext = info_dict.get('ext', '').strip().lower()
    if ext and not ext.startswith('.'):
        ext = f".{ext}"
    if ext:
        mime_type, _ = mimetypes.guess_type(f"file{ext}")
        if mime_type:
            if mime_type.startswith("image/"):
                return "image", ext
            if mime_type.startswith("video/"):
                return "video", ext
    format_id = info_dict.get('format_id', '').lower()
    vcodec = info_dict.get('vcodec', '').lower()
    if 'image' in format_id:
        return "image", ext
    if vcodec and vcodec != 'none':
        return "video", ext
    return "unknown", ext

async def live_typing_reply(message: Message, full_text: str, reply_markup=None, trigger_emoji_logic: bool = False, parse_mode=None) -> Message:
    lines = full_text.split('\n')
    chunked_lines = []
    for line in lines:
        words = line.split()
        chunks = []
        i = 0
        while i < len(words):
            take = 2
            chunks.append(" ".join(words[i:i+take]))
            i += take
        chunked_lines.append(chunks)
    max_chunks = max(len(c) for c in chunked_lines) if chunked_lines else 0
    current_lines = ["" for _ in chunked_lines]
    sent_msg = None
    modification_count = 0
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    protect = await is_content_protected(chat_id)
    for step in range(max_chunks):
        for line_idx, chunks in enumerate(chunked_lines):
            if step < len(chunks):
                if current_lines[line_idx]: current_lines[line_idx] += " " + chunks[step]
                else: current_lines[line_idx] = chunks[step]
        visible_text = "\n".join([line for line in current_lines if line])
        if not visible_text.strip(): continue
        if sent_msg is None:
            sent_msg = await message.reply(visible_text, protect_content=protect, parse_mode=parse_mode)
            modification_count = 0
            if trigger_emoji_logic:
                active_emoji_tasks[sent_msg.message_id] = None
        else:
            try:
                await sent_msg.edit_text(visible_text, parse_mode=parse_mode)
                modification_count += 1
            except Exception:
                pass
        if trigger_emoji_logic and modification_count == 1:
            spawn_emoji_task(sent_msg, trigger_by_user_id=user_id)
            trigger_emoji_logic = False
        await asyncio.sleep(0.3)
    if reply_markup and sent_msg:
        try: await sent_msg.edit_reply_markup(reply_markup=reply_markup)
        except Exception: pass
    if sent_msg:
        if trigger_emoji_logic:
            spawn_emoji_task(sent_msg, trigger_by_user_id=user_id)
        bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
        asyncio.create_task(delayed_react(chat_id, sent_msg.message_id, bot_emoji))
        user_emoji = get_smart_reaction(last_user_reaction, chat_id)
        asyncio.create_task(delayed_react(chat_id, sent_msg.message_id, user_emoji))
    return sent_msg

async def extract_and_download(target: str, tracker: ProgressTracker, mute_audio: bool = False):
    loop = asyncio.get_event_loop()
    fmt = 'bestvideo/best' if mute_audio else 'bestvideo+bestaudio/best'
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            current = d.get('downloaded_bytes', 0)
            if total > 0:
                asyncio.run_coroutine_threadsafe(tracker.update(current, total), loop)

    ydl_opts = {
        'format': fmt, 
        'outtmpl': '%(uploader)s_tmp.%(ext)s', 
        'noplaylist': True, 
        'quiet': True,
        'progress_hooks': [progress_hook]
    }
    search_target = target
    def sync_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            is_image_or_album = False
            downloaded_images = []
            if 'entries' in info:
                entries = list(info['entries'])
                if entries and any(analyze_media(e)[0] == "image" for e in entries if e):
                    is_image_or_album = True
                    for e in entries:
                        if e and analyze_media(e)[0] == "image":
                            filename = ydl.prepare_filename(e)
                            if os.path.exists(filename):
                                downloaded_images.append(filename)
                if not is_image_or_album:
                    if not info['entries']: return None, None, None, None, False, ""
                    info = info['entries'][0]
            else:
                media_type, _ = analyze_media(info)
                if media_type == "image":
                    is_image_or_album = True
                    filename = ydl.prepare_filename(info)
                    if os.path.exists(filename):
                        downloaded_images.append(filename)
            if is_image_or_album and downloaded_images:
                return downloaded_images, info.get('title', ''), info.get('uploader', ''), info.get('id', ''), True, ""
            raw_filename = ydl.prepare_filename(info)
            original_title = info.get('title', '')
            uploader = info.get('uploader', '')
            media_id = info.get('id', '')
            _, actual_ext = analyze_media(info)
            if not actual_ext:
                _, actual_ext = os.path.splitext(raw_filename)
            return raw_filename, original_title, uploader, media_id, False, actual_ext
    return await loop.run_in_executor(None, sync_download)

async def queue_worker():
    while True:
        message, target, user_id, cache_key = await download_queue.get()
        chat_id = message.chat.id
        
        content_text = message.text if message.text else (message.caption if message.caption else "")
        is_sticker_mode = "ستيكر" in content_text
        
        protect = True if is_sticker_mode else await is_content_protected(chat_id)
        
        async with aiosqlite.connect("bot_data.db") as db:
            async with db.execute("SELECT file_id, media_type, title FROM media_cache WHERE media_key = ?", (cache_key,)) as cursor:
                cached_row = await cursor.fetchone()
        
        sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
        combined_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ابلاغ الدعم", url="tg://user?id=8467593882")],
            [InlineKeyboardButton(text="رب العالمين", url=sub_link)]
        ])
        
        success_text = random.choice(SUCCESS_RESPONSES)
        
        if cached_row:
            file_id, media_type, title = cached_row
            last_sent_msg = None
            if is_sticker_mode:
                if media_type == "gif":
                    last_sent_msg = await message.reply_animation(animation=file_id, reply_markup=None, protect_content=True, has_spoiler=True)
                    if last_sent_msg:
                        bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                        asyncio.create_task(delayed_react(chat_id, last_sent_msg.message_id, bot_emoji))
                        user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                        asyncio.create_task(delayed_react(chat_id, last_sent_msg.message_id, user_emoji))
            else:
                if media_type == "album":
                    file_ids = file_id.split(",")
                    chunks = [file_ids[i:i + 8] for i in range(0, len(file_ids), 8)]
                    for i, chunk in enumerate(chunks):
                        media_group = [InputMediaDocument(media=fid) for fid in chunk]
                        album_msgs = await message.reply_media_group(media=media_group, protect_content=protect)
                        if album_msgs:
                            last_sent_msg = album_msgs[0]
                            for amsg in album_msgs:
                                bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                                asyncio.create_task(delayed_react(chat_id, amsg.message_id, bot_emoji))
                                user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                                asyncio.create_task(delayed_react(chat_id, amsg.message_id, user_emoji))
                        await asyncio.sleep(0.5)
                elif media_type == "video":
                    last_sent_msg = await message.reply_document(document=file_id, reply_markup=None, protect_content=protect)
                    if last_sent_msg:
                        bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                        asyncio.create_task(delayed_react(chat_id, last_sent_msg.message_id, bot_emoji))
                        user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                        asyncio.create_task(delayed_react(chat_id, last_sent_msg.message_id, user_emoji))
            
            if last_sent_msg:
                text_msg = await message.reply(text=success_text, reply_markup=combined_kb, protect_content=protect)
                spawn_emoji_task(text_msg, trigger_by_user_id=user_id)
                bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                asyncio.create_task(delayed_react(chat_id, text_msg.message_id, bot_emoji))
                user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                asyncio.create_task(delayed_react(chat_id, text_msg.message_id, user_emoji))
                download_queue.task_done()
                continue
                
        status_msg = await message.reply("انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا", protect_content=protect)
        try:
            await status_msg.react(reactions=[ReactionTypeEmoji(emoji="🔥")])
        except Exception:
            pass

        tracker = ProgressTracker(bot, chat_id, status_msg.message_id)
        file_path = None
        is_img_type = False
        try:
            res = await extract_and_download(target, tracker, mute_audio=is_sticker_mode)
            if res and res[0]:
                file_path, orig_title, uploader, media_id, is_img_type, actual_ext = res
                last_sent_msg = None
                if is_img_type:
                    if isinstance(file_path, list):
                        chunks = [file_path[i:i + 8] for i in range(0, len(file_path), 8)]
                        all_collected_ids = []
                        for i, chunk in enumerate(chunks):
                            media_group = [InputMediaDocument(media=FSInputFile(fp)) for fp in chunk]
                            album_msgs = await message.reply_media_group(media=media_group, protect_content=protect)
                            if album_msgs:
                                last_sent_msg = album_msgs[0]
                                for m in album_msgs:
                                    bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                                    asyncio.create_task(delayed_react(chat_id, m.message_id, bot_emoji))
                                    user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                                    asyncio.create_task(delayed_react(chat_id, m.message_id, user_emoji))
                                    if m.document:
                                        all_collected_ids.append(m.document.file_id)
                            await asyncio.sleep(0.5)
                        if all_collected_ids and not is_sticker_mode:
                            async with aiosqlite.connect("bot_data.db") as db:
                                await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, ",".join(all_collected_ids), "album", orig_title))
                                await db.commit()
                    try:
                        for fp in (file_path if isinstance(file_path, list) else [file_path]):
                            if os.path.exists(fp): os.remove(fp)
                    except Exception: pass
                else:
                    formatted_uploader = clean_and_format_text(uploader) if uploader else "MediA"
                    if not formatted_uploader.strip():
                        formatted_uploader = "MediA"
                    rand_9_digits = "".join([str(random.randint(0, 9)) for _ in range(9)])
                    new_file_name = f"{formatted_uploader} - {rand_9_digits}{actual_ext}"
                    new_file_path = new_file_name
                    try: 
                        os.rename(file_path, new_file_path)
                        file_path = new_file_path
                    except Exception: 
                        pass
                    
                    if is_sticker_mode:
                        last_sent_msg = await message.reply_animation(animation=FSInputFile(file_path), reply_markup=None, protect_content=True, has_spoiler=True)
                        if last_sent_msg and last_sent_msg.animation:
                            async with aiosqlite.connect("bot_data.db") as db:
                                await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, last_sent_msg.animation.file_id, "gif", orig_title))
                                await db.commit()
                    else:
                        last_sent_msg = await message.reply_document(document=FSInputFile(file_path), reply_markup=None, protect_content=protect)
                        if last_sent_msg and last_sent_msg.document:
                            async with aiosqlite.connect("bot_data.db") as db:
                                await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, last_sent_msg.document.file_id, "video", orig_title))
                                await db.commit()
                    if last_sent_msg:
                        bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                        asyncio.create_task(delayed_react(chat_id, last_sent_msg.message_id, bot_emoji))
                        user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                        asyncio.create_task(delayed_react(chat_id, last_sent_msg.message_id, user_emoji))
                
                try:
                    await status_msg.delete()
                except Exception:
                    pass

                if last_sent_msg:
                    text_msg = await message.reply(text=success_text, reply_markup=combined_kb, protect_content=protect)
                    spawn_emoji_task(text_msg, trigger_by_user_id=user_id)
                    bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                    asyncio.create_task(delayed_react(chat_id, text_msg.message_id, bot_emoji))
                    user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                    asyncio.create_task(delayed_react(chat_id, text_msg.message_id, user_emoji))
            else:
                try: await status_msg.delete()
                except Exception: pass
                await live_typing_reply(message, "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي", reply_markup=None, trigger_emoji_logic=True)
        except Exception:
            try: await status_msg.delete()
            except Exception: pass
            await live_typing_reply(message, "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي", reply_markup=None, trigger_emoji_logic=True)
        finally:
            if file_path and os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception: pass
            async with counter_lock:
                if user_id in user_task_counts:
                    user_task_counts[user_id] -= 1
                    if user_task_counts[user_id] <= 0: user_task_counts.pop(user_id, None)
            download_queue.task_done()

async def handle_random_replies(message: Message):
    global welcome_state
    if message.chat.type == "channel":
        return
        
    kb_dev = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="المطور", url="tg://user?id=8597653867")]])
    
    responses_pool = [
        "اهلين وياك بوت MediA تريد اشتغل دز\nرابط الفيديو التريده",
        "مو ناوي تستعملني وتشغلني مثل البوتات ؟!\nاضوج ترى ازعل واصيح المولاي يهينك",
        "من اشوف زبك يسعبل كسي وتذوب الروح انزل العيرك\nذليلة امصة ولباسي مشلوح",
        "انزع لباسي الك واكلك نيكني يبعد كل طموح شكني بعيرك\nوضرطني العافيه ترى فدوه الك اروح"
    ]
    
    selected_text = responses_pool[welcome_state]
    welcome_state = (welcome_state + 1) % 4
    
    await live_typing_reply(message, selected_text, reply_markup=kb_dev, trigger_emoji_logic=True)

# دالة الترجمة المعدلة باستخدام مكتبة googletrans الاستقراية لعام 2026
async def translate_text(text: str, target_lang: str) -> str:
    if not text:
        return ""
    loop = asyncio.get_event_loop()
    def process_translation():
        try:
            translator = Translator()
            translated = translator.translate(text, dest=target_lang)
            return clean_and_format_translation(translated.text, target_lang)
        except Exception:
            return text
    return await loop.run_in_executor(None, process_translation)

# فلتر يستقبل "دت" أو "ادت" لضمان ثبات عمل الأمر
@dp.message((F.text == "دت") | (F.text == "ادت"))
async def admin_cmd(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id
    is_group = message.chat.type in ["group", "supergroup"]
    is_channel = message.chat.type == "channel"
    
    user_emoji = get_smart_reaction(last_user_reaction, chat_id)
    asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))
        
    if is_all_admins(user_id):
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الزر")],
            [KeyboardButton(text="تبديل اللغه"), KeyboardButton(text="وضع اللغات")],
            [KeyboardButton(text="الغاء")]
        ], resize_keyboard=True)
        resp = await message.reply("تريد عرض رابط الزر دوس عرض الزر\nتريد تعين رابط الزر دوس تعيين الرابط", reply_markup=kb)
        spawn_emoji_task(resp, trigger_by_user_id=user_id)
        bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
        asyncio.create_task(delayed_react(message.chat.id, resp.message_id, bot_emoji))
    else:
        if not is_group and not is_channel:
            await handle_random_replies(message)

@dp.callback_query(F.data.startswith("show_cmds:"))
async def show_commands_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    creator_id = int(callback.data.split(":")[1])
    if user_id != creator_id:
        await callback.answer("شكد طفل وشكد منيوج نعلعلا ابوك\nونعلعلا نيج امك ياسكط", show_alert=True)
        return
    cmds_text = (
        "قفل / النقل \n"
        "فتح / الاشعارات \n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="مسح", callback_data=f"delete_panel:{creator_id}")]
    ])
    try:
        await callback.message.edit_text(text=cmds_text, reply_markup=kb)
        spawn_emoji_task(callback.message, trigger_by_user_id=user_id)
        bot_emoji = get_smart_reaction(last_bot_reaction, callback.message.chat.id)
        asyncio.create_task(delayed_react(callback.message.chat.id, callback.message.message_id, bot_emoji))
    except Exception:
        pass
    await callback.answer(cache_time=0)

@dp.callback_query(F.data.startswith("delete_panel:"))
async def delete_panel_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    creator_id = int(callback.data.split(":")[1])
    if user_id != creator_id:
        await callback.answer("شكد طفل وشكد منيوج نعلعلا ابوك\nونعلعلا نيج امك ياسكط", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer(cache_time=0)

@dp.message()
@dp.channel_post()
async def universal_handler(message: Message):
    global welcome_state, emoji_index
    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id
    is_group = message.chat.type in ["group", "supergroup"]
    is_channel = message.chat.type == "channel"
    protect = await is_content_protected(chat_id)
    
    cmd_cleaned = message.text.strip() if message.text else ""

    if cmd_cleaned in ["دت", "ادت"]:
        return

    if user_id > 0:
        if message.text == "/start":
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR IGNORE INTO users_log (user_id) VALUES (?)", (user_id,))
                await db.execute("INSERT OR IGNORE INTO translation_settings (user_id, lang, mode) VALUES (?, 'en', 0)", (user_id,))
                await db.commit()
                
    user_emoji = get_smart_reaction(last_user_reaction, chat_id)
    asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))

    is_service = (
        message.new_chat_members or 
        message.left_chat_member or 
        message.new_chat_title or 
        message.new_chat_photo or 
        message.delete_chat_photo or 
        message.group_chat_created or 
        message.supergroup_chat_created or 
        message.channel_chat_created or 
        message.message_auto_delete_timer_changed or 
        message.pinned_message or 
        message.invoice or 
        message.successful_payment or 
        message.user_shared or 
        message.chat_shared or 
        message.write_access_allowed or 
        message.video_chat_started or 
        message.video_chat_ended or 
        message.video_chat_participants_invited or 
        message.video_chat_scheduled or 
        message.forum_topic_created or 
        message.forum_topic_edited or 
        message.forum_topic_closed or 
        message.forum_topic_reopened or 
        message.general_forum_topic_hidden or 
        message.general_forum_topic_unhidden
    )
    if is_service:
        async with aiosqlite.connect("bot_data.db") as db:
            async with db.execute("SELECT status FROM chat_notifications WHERE chat_id = ?", (chat_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == "locked":
                    try: await message.delete()
                    except Exception: pass
                    return
                        
    if cmd_cleaned == "الاوامر":
        if is_all_admins(user_id) or (is_group and await is_user_owner(chat_id, user_id)) or is_channel or (not is_group and not is_channel):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="قفل / فتح", callback_data=f"show_cmds:{user_id}")],
                [InlineKeyboardButton(text="مسح", callback_data=f"delete_panel:{user_id}")],
            ])
            resp = await message.reply("الاوامر والتعليمات", reply_markup=kb, protect_content=protect)
            spawn_emoji_task(resp, trigger_by_user_id=user_id)
        else:
            if not is_group and not is_channel:
                await handle_random_replies(message)
        return
        
    if cmd_cleaned in ["قفل الاشعارات", "فتح الاشعارات"]:
        if is_group or is_channel or (not is_group and not is_channel):
            if is_channel or is_all_admins(user_id) or await is_user_owner(chat_id, user_id):
                status_to_set = "locked" if cmd_cleaned == "قفل الاشعارات" else "unlocked"
                async with aiosqlite.connect("bot_data.db") as db:
                    await db.execute("INSERT OR REPLACE INTO chat_notifications (chat_id, status) VALUES (?, ?)", (chat_id, status_to_set))
                    await db.commit()
                action_word = "قفل" if status_to_set == "locked" else "فتح"
                reply_txt = f"¹# - تم {action_word} الاشعارات مولاي\nيدلل تاج راسي"
                resp = await message.reply(reply_txt, protect_content=protect)
                spawn_emoji_task(resp, trigger_by_user_id=user_id)
        return
        
    if cmd_cleaned in ["قفل النقل", "فتح النقل"]:
        if is_channel or is_all_admins(user_id) or (is_group and await is_user_owner(chat_id, user_id)) or (not is_group and not is_channel):
            status_to_set = "locked" if cmd_cleaned == "قفل النقل" else "unlocked"
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR REPLACE INTO chat_protection (chat_id, status) VALUES (?, ?)", (chat_id, status_to_set))
                await db.commit()
            action_word = "قفل" if status_to_set == "locked" else "فتح"
            reply_txt = f"¹# - تم {action_word} النقل مولاي\nيدلل تاج راسي"
            new_protect = (status_to_set == "locked")
            resp = await message.reply(reply_txt, protect_content=new_protect)
            spawn_emoji_task(resp, trigger_by_user_id=user_id)
        return
        
    if cmd_cleaned in ["تعيين الرابط", "عرض الزر"] and not is_group and not is_channel:
        if is_all_admins(user_id):
            if cmd_cleaned == "تعيين الرابط":
                admin_states[user_id] = "waiting_link"
                kb_back = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="عودة")]], resize_keyboard=True)
                resp = await message.reply("ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", reply_markup=kb_back, protect_content=protect)
                spawn_emoji_task(resp, trigger_by_user_id=user_id)
            elif cmd_cleaned == "عرض الزر":
                kb_second_page = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="عودة")]], resize_keyboard=True)
                has_custom = await is_custom_link_set()
                if has_custom:
                    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
                    btn_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اشترك بالقناة", url=sub_link)]])
                else:
                    btn_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="تواصل مع المطور", url=DEFAULT_SUBSCRIBE_LINK)]])
                resp = await bot.send_message(
                    chat_id=chat_id,
                    text="اشترك بالقناة لو ماراح يشتغل\nوياك البوت ضروري عيني",
                    reply_markup=btn_kb,
                    reply_to_message_id=message.message_id,
                    protect_content=protect
                )
                spawn_emoji_task(resp, reply_markup=kb_second_page, trigger_by_user_id=user_id)
            return
            
    if cmd_cleaned == "تبديل اللغه" and not is_group and not is_channel:
        if is_all_admins(user_id):
            kb_langs_page = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="انكليزيه"), KeyboardButton(text="روسيه"), KeyboardButton(text="يابانيه")],
                [KeyboardButton(text="عودة")]
            ], resize_keyboard=True)
            async with emoji_lock:
                selected = EMOJI_SEQUENCE[emoji_index]
                emoji_index = (emoji_index + 1) % len(EMOJI_SEQUENCE)
            resp = await message.reply(selected, reply_markup=kb_langs_page, protect_content=protect)
            bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, resp.message_id, bot_emoji))
            return
            
    if cmd_cleaned in ["انكليزيه", "روسيه", "يابانيه"] and not is_group and not is_channel:
        if is_all_admins(user_id):
            if cmd_cleaned == "انكليزيه":
                target_lang = "en"
            elif cmd_cleaned == "روسيه":
                target_lang = "ru"
            else:
                target_lang = "ja"
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR REPLACE INTO translation_settings (user_id, lang, mode) VALUES (?, ?, (SELECT COALESCE(mode, 0) FROM translation_settings WHERE user_id = ?))", (user_id, target_lang, user_id))
                await db.commit()
            
            kb_next_mode = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="وضع اللغات")],
                [KeyboardButton(text="عودة")]
            ], resize_keyboard=True)
            
            resp = await message.reply("تم تبديل لغتك مثل ماتريد بعد كسي\nشم طيزي فدوه", reply_markup=kb_next_mode)
            spawn_emoji_task(resp, trigger_by_user_id=user_id)
            bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, resp.message_id, bot_emoji))
            return

    if cmd_cleaned == "وضع اللغات" and not is_group and not is_channel:
        if is_all_admins(user_id):
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR REPLACE INTO translation_settings (user_id, lang, mode) VALUES (?, (SELECT COALESCE(lang, 'en') FROM translation_settings WHERE user_id = ?), 1)", (user_id, user_id))
                await db.commit()
            kb_cancel_only = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="عودة")]], resize_keyboard=True)
            resp = await message.reply("اي شي تكتبه هسه راح اعتبره TrANSLATioN\nوادزلك الكلام بنفس شروطك الكتابيه ولغتك", reply_markup=kb_cancel_only, protect_content=protect)
            spawn_emoji_task(resp, trigger_by_user_id=user_id)
            return
            
    if cmd_cleaned == "الغاء" and not is_group and not is_channel:
        if is_all_admins(user_id):
            admin_states.pop(user_id, None)
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR REPLACE INTO translation_settings (user_id, lang, mode) VALUES (?, (SELECT COALESCE(lang, 'en') FROM translation_settings WHERE user_id = ?), 0)", (user_id, user_id))
                await db.commit()
            resp = await message.reply("صار وتدلل\nمنو يكدر يعصيك يبعد كسي اه", reply_markup=ReplyKeyboardRemove(), protect_content=protect)
            spawn_emoji_task(resp, trigger_by_user_id=user_id)
            return
            
    if cmd_cleaned == "عودة" and not is_group and not is_channel:
        if is_all_admins(user_id):
            admin_states.pop(user_id, None)
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR REPLACE INTO translation_settings (user_id, lang, mode) VALUES (?, (SELECT COALESCE(lang, 'en') FROM translation_settings WHERE user_id = ?), 0)", (user_id, user_id))
                await db.commit()
            kb_orig = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الزر")],
                [KeyboardButton(text="تبديل اللغه"), KeyboardButton(text="وضع اللغات")],
                [KeyboardButton(text="الغاء")]
            ], resize_keyboard=True)
            async with emoji_lock:
                selected = EMOJI_SEQUENCE[emoji_index]
                emoji_index = (emoji_index + 1) % len(EMOJI_SEQUENCE)
            resp = await message.reply(selected, reply_markup=kb_orig, protect_content=protect)
            bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, resp.message_id, bot_emoji))
            return
            
    if not is_group and not is_channel and is_all_admins(user_id) and admin_states.get(user_id) == "waiting_link":
        admin_states.pop(user_id, None)
        kb_orig = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الزر")],
            [KeyboardButton(text="تبديل اللغه"), KeyboardButton(text="وضع اللغات")],
            [KeyboardButton(text="الغاء")]
        ], resize_keyboard=True)
        if message.text:
            text_val = message.text.strip()
            pure_username = text_val
            if "t.me/" in text_val:
                parts = text_val.split("t.me/")
                if len(parts) > 1:
                    pure_username = parts[1].split('?')[0].split('/')[0]
            clean_user_to_check = pure_username.replace("@", "")
            username_len = len(clean_user_to_check)
            if 5 <= username_len <= 42 and STRICT_USERNAME_REGEX.match(pure_username):
                clean_url = get_clean_url(text_val)
                await set_setting("sub_link", clean_url)
                await set_setting("btn_text", "اشترك بالقناة")
                await set_setting("btn_style", "success")
                resp = await message.reply("تم تعيين زر الاشتراك العلني مثل ماردت\nسمعا وطاعة العيرك", reply_markup=kb_orig, protect_content=protect)
            else:
                resp = await message.reply("اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي", reply_markup=kb_orig, protect_content=protect)
        else:
            resp = await message.reply("اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي", reply_markup=kb_orig, protect_content=protect)
        spawn_emoji_task(resp, trigger_by_user_id=user_id)
        return
        
    content_text = message.text if message.text else (message.caption if message.caption else "")
    all_urls = ANY_URL_REGEX.findall(content_text)
    downloadable_urls = [url for url in all_urls if "t.me" not in url and "telegram.me" not in url]
    if downloadable_urls:
        if is_group and not await is_user_admin_or_owner(chat_id, user_id):
            return
        if not await check_force_subscription(user_id):
            force_kb = await get_force_sub_keyboard()
            await live_typing_reply(message, "اشترك بالقناة لو ماراح يشتغل\nوياك البوت ضروري عيني", reply_markup=force_kb, trigger_emoji_logic=True)
            return
        async with counter_lock:
            current_count = user_task_counts.get(user_id, 0)
            for url in downloadable_urls:
                if current_count >= 7: break
                current_count += 1; user_task_counts[user_id] = current_count
                
                is_sticker_mode = "ستيكر" in content_text
                cache_suffix = f"media_{url}_muted" if is_sticker_mode else f"media_{url}"
                await download_queue.put((message, url, user_id, cache_suffix))
        return
        
    if content_text.strip() in ["تعيين الرابط", "عرض الزر", "تبديل اللغه", "وضع اللغات", "الغاء", "عودة", "قفل النقل", "فتح النقل", "قفل الاشعارات", "فتح الاشعارات", "الاوامر", "انكليزيه", "روسيه", "يابانيه"]:
        return
        
    if is_group:
        if content_text.strip() == "بوت":
            await handle_random_replies(message)
            return
    
    if not is_channel:
        if cmd_cleaned and not ANY_URL_REGEX.findall(cmd_cleaned):
            async with aiosqlite.connect("bot_data.db") as db:
                async with db.execute("SELECT lang, mode FROM translation_settings WHERE user_id = ?", (user_id,)) as cursor:
                    t_row = await cursor.fetchone()
            if t_row and t_row[1] == 1 and t_row[0]:
                formatted_res = await translate_text(cmd_cleaned, t_row[0])
                if formatted_res.strip():
                    resp = await message.reply(formatted_res, protect_content=protect)
                    spawn_emoji_task(resp, trigger_by_user_id=user_id)
                    return
            else:
                has_eng_or_rus = bool(re.search(r'[a-zA-Zа-яА-ЯёЁ]', cmd_cleaned))
                if has_eng_or_rus:
                    formatted_res = clean_and_format_text(cmd_cleaned)
                    if formatted_res.strip():
                        resp = await message.reply(formatted_res, protect_content=protect)
                        spawn_emoji_task(resp, trigger_by_user_id=user_id)
                        return
        await handle_random_replies(message)

async def send_startup_notification():
    for admin_id in PRIMARY_ADMINS:
        try:
            protect = await is_content_protected(admin_id)
            msg = await bot.send_message(chat_id=admin_id, text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!", protect_content=protect)
            spawn_emoji_task(msg, custom_emoji="🧨", trigger_by_user_id=admin_id)
        except Exception:
            pass

async def main():
    await init_db()
    asyncio.create_task(queue_worker())
    asyncio.create_task(send_startup_notification())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
