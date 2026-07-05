import os
import re
import asyncio
import random
import aiosqlite
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ChatMemberUpdated, CallbackQuery, InputMediaDocument
from aiogram.filters import ChatMemberUpdatedFilter
import yt_dlp

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
DEFAULT_BUTTON_STYLE = "primary"

REACTIONS_POOL = ["🥰", "😡", "😘", "🍓", "🤣", "🤗", "😭"]
last_user_reaction = {}
last_bot_reaction = {}

ANY_URL_REGEX = re.compile(r'(https?://[^\s]+)')

STRICT_USERNAME_REGEX = re.compile(r'^@?(?=[a-zA-Z])[a-zA-Z0-9](?:[a-zA-Z0-9_]*[a-zA-Z0-9])?$')
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_notifications (
                chat_id INTEGER PRIMARY KEY,
                status TEXT
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
    btn_style = await get_setting("btn_style", DEFAULT_BUTTON_STYLE)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=sub_link, style=btn_style)]])

async def get_force_sub_keyboard() -> InlineKeyboardMarkup:
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اشترك بالقناة", url=sub_link, style="primary")]])

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
        await bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=[{"type": "emoji", "emoji": emoji}], is_big=False)
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

async def is_user_owner(chat_id: int, user_id: int) -> bool:
    if user_id in ADMIN_IDS: return True
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
    
    search_target = target

    def sync_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            
            is_image_or_album = False
            downloaded_images = []
            
            if 'entries' in info:
                entries = list(info['entries'])
                if entries and any(e.get('ext') in ['jpg', 'jpeg', 'png', 'webp'] or 'image' in e.get('format_id', '') for e in entries if e):
                    is_image_or_album = True
                    for e in entries:
                        if e:
                            filename = ydl.prepare_filename(e)
                            if os.path.exists(filename):
                                downloaded_images.append(filename)
                if not is_image_or_album:
                    if not info['entries']: return None, None, None, None, False
                    info = info['entries'][0]
            else:
                if info.get('ext') in ['jpg', 'jpeg', 'png', 'webp'] or 'image' in info.get('format_id', ''):
                    is_image_or_album = True
                    filename = ydl.prepare_filename(info)
                    if os.path.exists(filename):
                        downloaded_images.append(filename)

            if is_image_or_album and downloaded_images:
                return downloaded_images, info.get('title', 'Images'), info.get('uploader', 'Publisher'), info.get('id', 'img'), True

            raw_filename = ydl.prepare_filename(info)
            original_title = info.get('title', 'Media')
            uploader = info.get('uploader', 'Publisher')
            media_id = info.get('id', str(random.randint(100000, 999999)))
            return raw_filename, original_title, uploader, media_id, False
            
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
                audio_msg = await message.reply_audio(audio=file_id, caption="وهايهية اغنيتك تاج راسي شتريد بعد\nتدلل بعدقلبي", title=title, reply_markup=sub_kb)
                spawn_emoji_task(message)
                bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                asyncio.create_task(delayed_react(message.chat.id, audio_msg.message_id, bot_emoji))
            elif media_type == "album":
                file_ids = file_id.split(",")
                chunks = [file_ids[i:i + 8] for i in range(0, len(file_ids), 8)]
                for chunk in chunks:
                    media_group = [InputMediaDocument(media=fid) for fid in chunk]
                    album_msgs = await message.reply_media_group(media=media_group)
                    await asyncio.sleep(0.5)
                spawn_emoji_task(message)
                if album_msgs:
                    bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                    asyncio.create_task(delayed_react(message.chat.id, album_msgs[0].message_id, bot_emoji))
            else:
                video_msg = await message.reply_video(video=file_id, caption="وهذا هوة الفيديو كدامك بالكامل\nالمايعرفني يعرفني شكد قوي", reply_markup=sub_kb)
                spawn_emoji_task(message)
                bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                asyncio.create_task(delayed_react(message.chat.id, video_msg.message_id, bot_emoji))
            download_queue.task_done()
            continue

        proc_msg = "يتم العثور والبدء ب استكشاف طلبك\nسيتم تنفيذه الان" if is_audio else "يتم العثور والبدء ب استكشاف طلبك\nسيتم ارسال الميديا الان"
        status_msg = await live_typing_reply(message, proc_msg, reply_markup=sub_kb, trigger_emoji_logic=True)
        file_path = None
        is_img_type = False
        
        try:
            res = await extract_and_download(target, is_audio)
            if res and res[0]:
                file_path, orig_title, uploader, media_id, is_img_type = res
                
                if is_img_type:
                    if isinstance(file_path, list):
                        chunks = [file_path[i:i + 8] for i in range(0, len(file_path), 8)]
                        all_collected_ids = []
                        last_sent_group = None
                        
                        for chunk in chunks:
                            media_group = [InputMediaDocument(media=FSInputFile(fp)) for fp in chunk]
                            album_msgs = await message.reply_media_group(media=media_group)
                            if album_msgs:
                                last_sent_group = album_msgs
                                for m in album_msgs:
                                    if m.document:
                                        all_collected_ids.append(m.document.file_id)
                            await asyncio.sleep(0.5)
                        
                        spawn_emoji_task(message)
                        if all_collected_ids:
                            async with aiosqlite.connect("bot_data.db") as db:
                                await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, ",".join(all_collected_ids), "album", orig_title))
                                await db.commit()
                        if last_sent_group:
                            bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                            asyncio.create_task(delayed_react(message.chat.id, last_sent_group[0].message_id, bot_emoji))
                    try:
                        for fp in (file_path if isinstance(file_path, list) else [file_path]):
                            if os.path.exists(fp): os.remove(fp)
                    except Exception: pass
                else:
                    base, ext = os.path.splitext(file_path)
                    if is_audio:
                        sanitized_orig = sanitize_filename(orig_title)
                        new_title = format_english_title(sanitized_orig)
                        new_file_path = f"{new_title}{ext}"
                        try: os.rename(file_path, new_file_path); file_path = new_file_path
                        except Exception: pass

                        audio_msg = await message.reply_audio(audio=FSInputFile(file_path), caption="وهايهية اغنيتك تاج راسي شتريد بعد\nتدلل بعدقلبي", title=new_title, reply_markup=sub_kb)
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

                        video_msg = await message.reply_video(video=FSInputFile(file_path), caption="وهذا هوة الفيديو كدامك بالكامل\nالمايعرفني يعرفني شكد قوي", reply_markup=sub_kb)
                        spawn_emoji_task(message)
                        if video_msg and video_msg.video:
                            async with aiosqlite.connect("bot_data.db") as db:
                                await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, video_msg.video.file_id, "video", orig_title))
                                await db.commit()
                        bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                        asyncio.create_task(delayed_react(message.chat.id, video_msg.message_id, bot_emoji))
            else:
                if status_msg: await status_msg.delete()
                await live_typing_reply(message, "الرابط غير مدعوم او لم يتم العثور عليه عزيزي", reply_markup=sub_kb, trigger_emoji_logic=True)
        except Exception:
            if status_msg: await status_msg.delete()
            await live_typing_reply(message, "الرابط غير مدعوم او لم يتم العثور عليه عزيزي", reply_markup=sub_kb, trigger_emoji_logic=True)
        finally:
            if not is_img_type and file_path and os.path.exists(file_path):
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
    if welcome_state:
        kb_primary = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="المطور", url="tg://user?id=8597653867", style="primary")]])
        await live_typing_reply(message, "اهلين وياك بوت MediA تريد اشتغل دز\nرابط الفيديو التريده", reply_markup=kb_primary, trigger_emoji_logic=True)
        welcome_state = False
    else:
        kb_danger = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]])
        await live_typing_reply(message, "مو ناوي تستعملني عدل?! تريد اضوج\nترى ازعل واصيح المولاي يهينك", reply_markup=kb_danger, trigger_emoji_logic=True)
        welcome_state = True

@dp.message(F.text == "ادت")
async def admin_cmd(message: Message):
    if message.from_user.id in ADMIN_IDS:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="تعيين رابط زر الاشتراك"), KeyboardButton(text="عرض الزر")]], resize_keyboard=True)
        await message.reply("تريد تغير اسم الزر دوس تغيير اسم الزر\nتريد تعين رابط الزر دوس تعيين الرابط", reply_markup=kb)
        spawn_emoji_task(message)
    else:
        is_group = message.chat.type in ["group", "supergroup"]
        if not is_group or (is_group and await is_user_admin_or_owner(message.chat.id, message.from_user.id, force_update=True)):
            bot_emoji = get_smart_reaction(last_user_reaction, message.chat.id)
            asyncio.create_task(delayed_react(message.chat.id, message.message_id, bot_emoji, delay=0.0))

@dp.callback_query(F.data == "show_cmds")
async def show_commands_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    is_group = callback.message.chat.type in ["group", "supergroup"]
    
    allowed = False
    if user_id in ADMIN_IDS:
        allowed = True
    elif is_group:
        allowed = await is_user_owner(chat_id, user_id)
        
    if not allowed:
        await callback.answer("شكد طفل وشكد منيوج نعلعلا ابوك\nونعلعلا نيج امك ياسكط", show_alert=True)
        return

    cmds_text = "قفل / فتح الاشعارات\nادت"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="عودة", callback_data="back_main", style="success")]
    ])
    try:
        await callback.message.edit_text(text=cmds_text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "back_main")
async def back_main_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    is_group = callback.message.chat.type in ["group", "supergroup"]
    
    allowed = False
    if user_id in ADMIN_IDS:
        allowed = True
    elif is_group:
        allowed = await is_user_owner(chat_id, user_id)
        
    if not allowed:
        await callback.answer("شكد طفل وشكد منيوج نعلعلا ابوك\nونعلعلا نيج امك ياسكط", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="قفل / فتح", callback_data="show_cmds", style="primary")],
        [InlineKeyboardButton(text="مسح", callback_data="delete_panel", style="danger")]
    ])
    try:
        await callback.message.edit_text(text="الاوامر", reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "delete_panel")
async def delete_panel_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    is_group = callback.message.chat.type in ["group", "supergroup"]
    
    allowed = False
    if user_id in ADMIN_IDS:
        allowed = True
    elif is_group:
        allowed = await is_user_owner(chat_id, user_id)
        
    if not allowed:
        await callback.answer("شكد طفل وشكد منيوج نعلعلا ابوك\nونعلعلا نيج امك ياسكط", show_alert=True)
        return

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

@dp.message()
async def universal_handler(message: Message):
    global welcome_state
    user_id = message.from_user.id
    chat_id = message.chat.id
    is_group = message.chat.type in ["group", "supergroup"]

    if message.reply_to_message and message.text and message.text.strip() == "ستيكر":
        if not is_group or (is_group and await is_user_admin_or_owner(chat_id, user_id)):
            rep = message.reply_to_message
            video_file_id = None
            if rep.video:
                video_file_id = rep.video.file_id
            elif rep.document and rep.document.mime_type and rep.document.mime_type.startswith("video/"):
                video_file_id = rep.document.file_id
            
            if video_file_id:
                user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))
                sub_kb = await get_sub_keyboard()
                gif_msg = await message.reply_animation(animation=video_file_id, reply_markup=sub_kb)
                spawn_emoji_task(message)
                bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                asyncio.create_task(delayed_react(chat_id, gif_msg.message_id, bot_emoji))
                return

    if is_group:
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
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        return

    if message.text and message.text.strip() == "الاوامر":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="قفل / فتح", callback_data="show_cmds", style="primary")],
            [InlineKeyboardButton(text="مسح", callback_data="delete_panel", style="danger")]
        ])
        await message.reply("الاوامر", reply_markup=kb)
        spawn_emoji_task(message)
        return

    if message.text and message.text.strip() in ["قفل الاشعارات", "فتح الاشعارات"]:
        if is_group:
            if await is_user_owner(chat_id, user_id):
                status_to_set = "locked" if message.text.strip() == "قفل الاشعارات" else "unlocked"
                async with aiosqlite.connect("bot_data.db") as db:
                    await db.execute("INSERT OR REPLACE INTO chat_notifications (chat_id, status) VALUES (?, ?)", (chat_id, status_to_set))
                    await db.commit()
                
                action_word = "قفل" if status_to_set == "locked" else "فتح"
                reply_txt = f"¹# - تم {action_word} الاشعارات مولاي\nيدلل تاج راسي"
                
                await message.reply(reply_txt)
                spawn_emoji_task(message)
            return

    if message.text and message.text.strip() == "بوت":
        if not is_group or (is_group and await is_user_admin_or_owner(chat_id, user_id, force_update=True)):
            user_emoji = get_smart_reaction(last_user_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))
            await handle_random_replies(message)
        return

    if message.text and message.text != "ادت" and message.text not in ["تعيين رابط زر الاشتراك", "عرض الزر", "الغاء"] and message.text.strip() != "بوت":
        if not is_group or (is_group and await is_user_admin_or_owner(chat_id, user_id)):
            user_emoji = get_smart_reaction(last_user_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))

    if message.text == "الغاء" and user_id in ADMIN_IDS:
        admin_states.pop(user_id, None)
        await message.reply("صار وتدلل\nمنو يكدر يعصيك يبعد كسي اه", reply_markup=ReplyKeyboardRemove())
        spawn_emoji_task(message)
        return

    if user_id in ADMIN_IDS and admin_states.get(user_id) == "waiting_link":
        admin_states.pop(user_id, None)
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
                await set_setting("btn_style", "primary")
                await message.reply("تم تعيين زر الاشتراك العلني مثل ماردت\nسمعا وطاعة العيرك", reply_markup=ReplyKeyboardRemove())
            else:
                await message.reply("اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي", reply_markup=ReplyKeyboardRemove())
        else:
            await message.reply("اهo ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي", reply_markup=ReplyKeyboardRemove())
        spawn_emoji_task(message)
        return

    if message.text == "تعيين رابط زر الاشتراك" and user_id in ADMIN_IDS:
        admin_states[user_id] = "waiting_link"
        kb_cancel = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="الغاء")]], resize_keyboard=True)
        await message.reply("ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", reply_markup=kb_cancel)
        spawn_emoji_task(message)
        return

    if message.text == "عرض الزر" and user_id in ADMIN_IDS:
        sub_kb = await get_sub_keyboard()
        await message.reply("هيج صار الزر بعد عيني دوس وشوف الرابط\nيشتغل لو لا", reply_markup=sub_kb)
        spawn_emoji_task(message)
        return

    if not message.text:
        if not is_group: await handle_random_replies(message)
        return

    all_urls = ANY_URL_REGEX.findall(message.text)
    
    if all_urls:
        if not await check_force_subscription(user_id):
            force_kb = await get_force_sub_keyboard()
            await live_typing_reply(message, "اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني", reply_markup=force_kb, trigger_emoji_logic=True)
            return
            
        async with counter_lock:
            current_count = user_task_counts.get(user_id, 0)
            for url in all_urls:
                if current_count >= 7: break
                current_count += 1; user_task_counts[user_id] = current_count
                await download_queue.put((message, url, user_id, False, f"media_{url}"))
        return

    if not is_group: await handle_random_replies(message)

async def send_startup_notification():
    for admin_id in ADMIN_IDS:
        try:
            msg = await bot.send_message(chat_id=admin_id, text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!")
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
