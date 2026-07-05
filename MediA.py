import os
import re
import asyncio
import random
import aiosqlite
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ReactionTypeEmoji
import yt_dlp

class BotMessages:
    RESP_1 = "اهلين وياك بوت MUsic تريد اشتغل\nدز لو رابط لو يوت وكول عنوان اغنيتك"
    RESP_2 = "مو ناوي تستعملني عدل?! تريد اضوج\nترى ازعل واصيح المولاي يهينك"
    
    PROCESSING_AUDIO = "يتم العثور والبدء ب استكشاف طلبك\nسيتم تنفيذه الان"
    PROCESSING_VIDEO = "يتم العثور والبدء ب استكشاف طلبك\nسيتم ارسال الفيديو الان"
    
    NOT_FOUND = "الرابط غير مدعوم او العنوان لم يتم العثور\nعليه عزيزي"
    SUCCESS_AUDIO = "وهايهية اغنيتك تاج راسي شتريد بعد\nتدلل بعدقلبي"
    SUCCESS_VIDEO = "وهذا هوة الفيديو كدامك بالكامل\nالمايعرفني يعرفني شكد قوي"
    
    ADMIN_MENU = "تريد تغير اسم الزر دوس تغيير اسم الزر\nتريد تعين رابط الزر دوس تعيين الرابط"
    ASK_LINK = "ارسل يوزر / رابط القناة او الكروب\nيلا مولاي"
    BAD_LINK = "اهو لاتمضرط وياي مو راح اضوج\nهوف منك مولاي"
    SET_SUCCESS = "تم تعيين زر الاشتراك العلني مثل ماردت\nسمعا وطاعة العيرك"
    PREVIEW_MSG = "هيج صار الزر بعد عيني دوس وشوف الرابط\nيشتغل لو لا"
    CANCEL_MSG = "صار وتدلل\nمنو يكدر يعصيك يبعد كسي اه"
    
    FORCE_SUB = "اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني"
    
    STARTUP_MSG = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

download_queue = asyncio.Queue()
user_task_counts = {}
counter_lock = asyncio.Lock()

welcome_state = True
active_emoji_tasks = {}
admin_states = {}

ADMIN_IDS = [8597653867, 8467593882]
DEFAULT_SUBSCRIBE_LINK = "tg://user?id=8597653867"
DEFAULT_BUTTON_TEXT = "رب العالمين"

REACTIONS_POOL = ["🥰", "😡", "😘", "🍓", "🤣", "🤗", "😭"]
last_user_reaction = {}
last_bot_reaction = {}

YOUTUBE_REGEX = re.compile(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11})')
TIKTOK_REGEX = re.compile(r'https?://(?:vm\.tiktok\.com/|v[td]\.tiktok\.com/|www\.tiktok\.com/@[\w.-]+/video/\d+)')
REDGIFS_REGEX = re.compile(r'https?://(?:www\.)?redgifs\.com/(?:watch|gifs)/[\w-]+')
CHANNEL_USER_REGEX = re.compile(r'^(https?://)?(www\.)?(t\.me/)?(joinchat/)?(⚡️)?[a-zA-Z][a-zA-Z0-9]{3,30}(?<!_)(?<![0-9])_?[a-zA-Z0-9]+(?<!_)$|^@[a-zA-Z][a-zA-Z0-9_]{3,30}(?<!_)$')

async def init_db():
    async with aiosqlite.connect("bot_data.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS permissions_cache (
                chat_id INTEGER,
                user_id INTEGER,
                is_admin INTEGER,
                expires_at REAL,
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
        await db.commit()

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

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\/*?:"<>|]', '', name).strip()
    return cleaned if cleaned else "Media_File"

def format_english_title(title: str) -> str:
    return re.sub(r'[atnmgfujl]', lambda m: m.group(0).upper(), title.lower())

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

async def check_force_subscription(user_id: int) -> bool:
    if user_id in ADMIN_IDS: return True
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    target_chat = extract_channel_chat_id(sub_link)
    if not target_chat: return True
    try:
        member = await bot.get_chat_member(chat_id=target_chat, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return True

def get_clean_url(input_str: str) -> str:
    input_str = input_str.strip()
    if input_str.startswith("@"): return f"https://t.me/{input_str[1:]}"
    if input_str.startswith("http://") or input_str.startswith("https://"): return input_str
    if input_str.startswith("t.me/"): return f"https://{input_str}"
    return f"https://t.me/{input_str}"

async def get_sub_keyboard() -> InlineKeyboardMarkup:
    btn_text = await get_setting("btn_text", DEFAULT_BUTTON_TEXT)
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=sub_link, style="success")]])

async def get_force_sub_keyboard() -> InlineKeyboardMarkup:
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اشترك بالقناة", url=sub_link, style="danger")]])

def get_smart_reaction(last_reaction_dict, key: int) -> str:
    last = last_reaction_dict.get(key)
    available = [r for r in REACTIONS_POOL if r != last]
    chosen = random.choice(available)
    last_reaction_dict[key] = chosen
    return chosen

async def delayed_react(chat_id: int, message_id: int, emoji: str, delay: float = None):
    if delay is None: delay = random.choice([2.4, 3.6, 4.8])
    await asyncio.sleep(delay)
    try:
        await bot.set_message_reaction(
            chat_id=chat_id, 
            message_id=message_id, 
            reaction=[ReactionTypeEmoji(emoji=emoji)], 
            is_big=False
        )
    except Exception:
        pass

async def is_user_admin_or_owner(chat_id: int, user_id: int, force_update: bool = False) -> bool:
    if user_id in ADMIN_IDS: return True
    current_time = time.time()
    if not force_update:
        async with aiosqlite.connect("bot_data.db") as db:
            async with db.execute("SELECT is_admin, expires_at FROM permissions_cache WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    is_admin, expires_at = row
                    if current_time < expires_at: return bool(is_admin)
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        res = member.status in ["administrator", "creator"]
    except Exception:
        res = False
    async with aiosqlite.connect("bot_data.db") as db:
        await db.execute("INSERT OR REPLACE INTO permissions_cache (chat_id, user_id, is_admin, expires_at) VALUES (?, ?, ?, ?)", (chat_id, user_id, int(res), current_time + 10.0))
        await db.commit()
    return res

async def emoji_cycle_worker(msg: Message):
    try:
        while True:
            await asyncio.sleep(7)
            await msg.edit_text("💅🏻")
            await asyncio.sleep(3)
            await msg.edit_text("🍕")
            await asyncio.sleep(6)
            await msg.edit_text("🍔")
            await asyncio.sleep(7)
            await msg.edit_text("🫦")
    except asyncio.CancelledError:
        pass
    except Exception:
        pass

def spawn_emoji_task(message: Message):
    async def trigger():
        try:
            emoji_msg = await message.reply("🫦")
            task = asyncio.create_task(emoji_cycle_worker(emoji_msg))
            chat_id = message.chat.id
            if chat_id not in active_emoji_tasks:
                active_emoji_tasks[chat_id] = []
            active_emoji_tasks[chat_id].append(task)
            if len(active_emoji_tasks[chat_id]) > 3:
                oldest_task = active_emoji_tasks[chat_id].pop(0)
                oldest_task.cancel()
        except Exception:
            pass
    asyncio.create_task(trigger())

async def live_typing_reply(message: Message, full_text: str, reply_markup=None, trigger_emoji_logic: bool = False) -> Message:
    lines = full_text.split('\n')
    chunked_lines = []
    for line in lines:
        words = line.split()
        chunks = []
        i = 0
        toggle = True
        while i < len(words):
            take = 3 if toggle else 2
            chunks.append(" ".join(words[i:i+take]))
            i += take
            toggle = not toggle
        chunked_lines.append(chunks)
    
    max_chunks = max(len(c) for c in chunked_lines) if chunked_lines else 0
    current_lines = ["" for _ in chunked_lines]
    sent_msg = None
    modification_count = 0
    
    for step in range(max_chunks):
        for line_idx, chunks in enumerate(chunked_lines):
            if step < len(chunks):
                if current_lines[line_idx]: current_lines[line_idx] += " " + chunks[step]
                else: current_lines[line_idx] = chunks[step]
                    
        visible_text = "\n".join([line for line in current_lines if line])
        if not visible_text.strip(): continue
            
        if sent_msg is None:
            sent_msg = await message.reply(visible_text)
            modification_count = 0
        else:
            try:
                await sent_msg.edit_text(visible_text)
                modification_count += 1
            except Exception:
                pass
                
        if trigger_emoji_logic and modification_count == 2:
            spawn_emoji_task(message)
            trigger_emoji_logic = False
            
        await asyncio.sleep(0.3)
        
    if reply_markup and sent_msg:
        try: await sent_msg.edit_reply_markup(reply_markup=reply_markup)
        except Exception: pass
            
    if sent_msg:
        if trigger_emoji_logic:
            spawn_emoji_task(message)
        bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
        asyncio.create_task(delayed_react(message.chat.id, sent_msg.message_id, bot_emoji))
        
    return sent_msg

async def extract_and_download(target: str, is_audio: bool):
    loop = asyncio.get_event_loop()
    if is_audio:
        ydl_opts = {'format': 'bestaudio/best', 'outtmpl': '%(title)s.%(ext)s', 'noplaylist': True, 'quiet': True}
    else:
        ydl_opts = {'format': 'bestvideo+bestaudio/best', 'outtmpl': '%(uploader)s_tmp.%(ext)s', 'noplaylist': True, 'quiet': True}
    search_target = target if (target.startswith("http://") or target.startswith("https://")) else f"ytsearch1:{target}"

    def sync_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            if 'entries' in info:
                if not info['entries']: return None, None, None
                info = info['entries'][0]
            raw_filename = ydl.prepare_filename(info)
            original_title = info.get('title', 'Audio')
            uploader = info.get('uploader', 'Publisher')
            media_id = info.get('id', str(random.randint(100000, 999999)))
            return raw_filename, original_title, uploader, media_id
            
    return await loop.run_in_executor(None, sync_download)

async def queue_worker():
    while True:
        message, target, user_id, is_audio, cache_key = await download_queue.get()
        async with aiosqlite.connect("bot_data.db") as db:
            async with db.execute("SELECT file_id, media_type, title FROM media_cache WHERE media_key = ?", (cache_key,)) as cursor:
                cached_row = await cursor.fetchone()
                
        sub_kb = await get_sub_keyboard()
        if cached_row:
            file_id, media_type, title = cached_row
            if media_type == "audio":
                audio_msg = await message.reply_audio(audio=file_id, caption=BotMessages.SUCCESS_AUDIO, title=title, reply_markup=sub_kb)
                spawn_emoji_task(message)
                bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                asyncio.create_task(delayed_react(message.chat.id, audio_msg.message_id, bot_emoji))
            else:
                video_msg = await message.reply_video(video=file_id, caption=BotMessages.SUCCESS_VIDEO, reply_markup=sub_kb)
                spawn_emoji_task(message)
                bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                asyncio.create_task(delayed_react(message.chat.id, video_msg.message_id, bot_emoji))
            download_queue.task_done()
            continue

        proc_msg = BotMessages.PROCESSING_AUDIO if is_audio else BotMessages.PROCESSING_VIDEO
        status_msg = await live_typing_reply(message, proc_msg, reply_markup=sub_kb, trigger_emoji_logic=True)
        file_path = None
        
        try:
            res = await extract_and_download(target, is_audio)
            if res and res[0] and os.path.exists(res[0]):
                file_path, orig_title, uploader, media_id = res
                base, ext = os.path.splitext(file_path)
                
                if is_audio:
                    sanitized_orig = sanitize_filename(orig_title)
                    new_title = format_english_title(sanitized_orig)
                    new_file_path = f"{new_title}{ext}"
                    try: os.rename(file_path, new_file_path); file_path = new_file_path
                    except Exception: pass

                    audio_msg = await message.reply_audio(audio=FSInputFile(file_path), caption=BotMessages.SUCCESS_AUDIO, title=new_title, reply_markup=sub_kb)
                    spawn_emoji_task(message)
                    if audio_msg and audio_msg.audio:
                        async with aiosqlite.connect("bot_data.db") as db:
                            await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, audio_msg.audio.file_id, "audio", new_title))
                            await db.commit()
                    bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                    asyncio.create_task(delayed_react(message.chat.id, audio_msg.message_id, bot_emoji))
                else:
                    rand_suffix = "".join([str(random.randint(0, 9)) for _ in range(9)])
                    sanitized_uploader = sanitize_filename(uploader)
                    clean_uploader = re.sub(r'[^\w\-]', '', sanitized_uploader)
                    if not clean_uploader: clean_uploader = "Publisher"
                    new_file_path = f"{clean_uploader}{rand_suffix}{ext}"
                    try: os.rename(file_path, new_file_path); file_path = new_file_path
                    except Exception: pass

                    video_msg = await message.reply_video(video=FSInputFile(file_path), caption=BotMessages.SUCCESS_VIDEO, reply_markup=sub_kb)
                    spawn_emoji_task(message)
                    if video_msg and video_msg.video:
                        async with aiosqlite.connect("bot_data.db") as db:
                            await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, video_msg.video.file_id, "video", orig_title))
                            await db.commit()
                    bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                    asyncio.create_task(delayed_react(message.chat.id, video_msg.message_id, bot_emoji))
            else:
                if status_msg: await status_msg.delete()
                await live_typing_reply(message, BotMessages.NOT_FOUND, reply_markup=sub_kb, trigger_emoji_logic=True)
                
        except Exception:
            if status_msg: await status_msg.delete()
            await live_typing_reply(message, BotMessages.NOT_FOUND, reply_markup=sub_kb, trigger_emoji_logic=True)
        finally:
            if file_path and os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception: pass
            if status_msg:
                try: await status_msg.delete()
                except Exception: pass
            async with counter_lock:
                if user_id in user_task_counts:
                    user_task_counts[user_id] -= 1
                    if user_task_counts[user_id] <= 0: user_task_counts.pop(user_id, None)
            download_queue.task_done()

async def handle_random_replies(message: Message):
    global welcome_state
    if message.text and (YOUTUBE_REGEX.search(message.text) or TIKTOK_REGEX.search(message.text) or REDGIFS_REGEX.search(message.text)):
        sub_kb = await get_sub_keyboard()
        await live_typing_reply(message, BotMessages.NOT_FOUND, reply_markup=sub_kb, trigger_emoji_logic=True)
        return

    if welcome_state:
        kb_primary = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="المطور", url="tg://user?id=8597653867", style="primary")]])
        await live_typing_reply(message, BotMessages.RESP_1, reply_markup=kb_primary, trigger_emoji_logic=True)
        welcome_state = False
    else:
        kb_danger = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]])
        await live_typing_reply(message, BotMessages.RESP_2, reply_markup=kb_danger, trigger_emoji_logic=True)
        welcome_state = True

@dp.message(F.text == "ادت")
async def admin_cmd(message: Message):
    if message.from_user.id in ADMIN_IDS:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="تعيين رابط زر الاشتراك"), KeyboardButton(text="عرض الزر")]], resize_keyboard=True)
        await message.reply(BotMessages.ADMIN_MENU, reply_markup=kb)
        spawn_emoji_task(message)
    else:
        is_group = message.chat.type in ["group", "supergroup"]
        if not is_group or (is_group and await is_user_admin_or_owner(message.chat.id, message.from_user.id, force_update=True)):
            bot_emoji = get_smart_reaction(last_user_reaction, message.chat.id)
            asyncio.create_task(delayed_react(message.chat.id, message.message_id, bot_emoji, delay=0.0))

@dp.message()
async def universal_handler(message: Message):
    global welcome_state
    user_id = message.from_user.id
    chat_id = message.chat.id
    is_group = message.chat.type in ["group", "supergroup"]

    if message.text and message.text.strip() == "بوت":
        if not is_group or (is_group and await is_user_admin_or_owner(chat_id, user_id, force_update=True)):
            user_emoji = get_smart_reaction(last_user_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))
            await handle_random_replies(message)
        return

    if message.text and message.text.strip() == "يوت":
        if not is_group or (is_group and await is_user_admin_or_owner(chat_id, user_id, force_update=True)):
            if not await check_force_subscription(user_id):
                force_kb = await get_force_sub_keyboard()
                await live_typing_reply(message, BotMessages.FORCE_SUB, reply_markup=force_kb, trigger_emoji_logic=True)
                return
            special_emoji = random.choice(["🌭", "🍌"])
            asyncio.create_task(delayed_react(chat_id, message.message_id, special_emoji, delay=0.0))
            spawn_emoji_task(message)
        return

    if message.text and message.text != "ادت" and message.text not in ["تعيين رابط زر الاشتراك", "عرض الزر", "إلغاء"] and message.text.strip() != "بوت" and message.text.strip() != "يوت":
        if not is_group or (is_group and await is_user_admin_or_owner(chat_id, user_id)):
            user_emoji = get_smart_reaction(last_user_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))

    if message.text == "إلغاء" and user_id in ADMIN_IDS:
        admin_states.pop(user_id, None)
        await message.reply(BotMessages.CANCEL_MSG, reply_markup=ReplyKeyboardRemove())
        spawn_emoji_task(message)
        return

    if user_id in ADMIN_IDS and admin_states.get(user_id) == "waiting_link":
        admin_states.pop(user_id, None)
        if message.text and CHANNEL_USER_REGEX.match(message.text.strip()):
            clean_url = get_clean_url(message.text)
            await set_setting("sub_link", clean_url)
            await set_setting("btn_text", "اشترك بالقناة")
            await message.reply(BotMessages.SET_SUCCESS, reply_markup=ReplyKeyboardRemove())
        else:
            await message.reply(BotMessages.BAD_LINK, reply_markup=ReplyKeyboardRemove())
        spawn_emoji_task(message)
        return

    if message.text == "تعيين رابط زر الاشتراك" and user_id in ADMIN_IDS:
        admin_states[user_id] = "waiting_link"
        kb_cancel = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="إلغاء")]], resize_keyboard=True)
        await message.reply(BotMessages.ASK_LINK, reply_markup=kb_cancel)
        spawn_emoji_task(message)
        return

    if message.text == "عرض الزر" and user_id in ADMIN_IDS:
        sub_kb = await get_sub_keyboard()
        await message.reply(BotMessages.PREVIEW_MSG, reply_markup=sub_kb)
        spawn_emoji_task(message)
        return

    if not message.text:
        if not is_group: await handle_random_replies(message)
        return

    yt_urls = YOUTUBE_REGEX.findall(message.text)
    tt_urls = TIKTOK_REGEX.findall(message.text)
    rg_urls = REDGIFS_REGEX.findall(message.text)
    
    if yt_urls or tt_urls or rg_urls:
        if not await check_force_subscription(user_id):
            force_kb = await get_force_sub_keyboard()
            await live_typing_reply(message, BotMessages.FORCE_SUB, reply_markup=force_kb, trigger_emoji_logic=True)
            return
            
        async with counter_lock:
            current_count = user_task_counts.get(user_id, 0)
            for url in yt_urls:
                if current_count >= 7: break
                current_count += 1; user_task_counts[user_id] = current_count
                await download_queue.put((message, url, user_id, True, f"yt_{url}"))
            for url in tt_urls:
                if current_count >= 7: break
                current_count += 1; user_task_counts[user_id] = current_count
                await download_queue.put((message, url, user_id, False, f"tt_{url}"))
            for url in rg_urls:
                if current_count >= 7: break
                current_count += 1; user_task_counts[user_id] = current_count
                await download_queue.put((message, url, user_id, False, f"rg_{url}"))
        return

    if message.text.startswith("يوت"):
        if not await check_force_subscription(user_id):
            force_kb = await get_force_sub_keyboard()
            await live_typing_reply(message, BotMessages.FORCE_SUB, reply_markup=force_kb, trigger_emoji_logic=True)
            return
        query = message.text[3:].strip()
        if query:
            async with counter_lock:
                current_count = user_task_counts.get(user_id, 0)
                if current_count < 7:
                    user_task_counts[user_id] = current_count + 1
                    await download_queue.put((message, query, user_id, True, f"query_{query}"))
            return

    if not is_group: await handle_random_replies(message)

async def send_startup_notification():
    for admin_id in ADMIN_IDS:
        try:
            msg = await bot.send_message(chat_id=admin_id, text=BotMessages.STARTUP_MSG)
            spawn_emoji_task(msg)
        except Exception:
            pass

async def main():
    await init_db()
    asyncio.create_task(queue_worker())
    asyncio.create_task(send_startup_notification())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
