import os
import re
import asyncio
import random
import aiosqlite
import time
import mimetypes
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

PRIMARY_ADMINS = [8597653867, 8467593882]
dynamic_admins = set()

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

async def init_db():
    async with aiosqlite.connect("bot_data.db") as db:
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
            CREATE TABLE IF NOT EXISTS dynamic_admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.commit()
        
    await load_dynamic_admins()

async def load_dynamic_admins():
    global dynamic_admins
    async with aiosqlite.connect("bot_data.db") as db:
        async with db.execute("SELECT user_id FROM dynamic_admins") as cursor:
            rows = await cursor.fetchall()
            dynamic_admins = {row[0] for row in rows}

def is_all_admins(user_id: int) -> bool:
    return user_id in PRIMARY_ADMINS or user_id in dynamic_admins

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
    if is_all_admins(user_id): return True
    sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
    if sub_link == DEFAULT_SUBSCRIBE_LINK: return True
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

async def get_dynamic_media_keyboard(user_id: int) -> InlineKeyboardMarkup:
    has_custom = await is_custom_link_set()
    if not has_custom:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="رب العالمين", url=DEFAULT_SUBSCRIBE_LINK, style="primary")]])
    
    is_subscribed = await check_force_subscription(user_id)
    if is_subscribed:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="تواصل مع المطور", url=DEFAULT_SUBSCRIBE_LINK, style="success")]])
    else:
        sub_link = await get_setting("sub_link", DEFAULT_SUBSCRIBE_LINK)
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اشترك بالقناة", url=sub_link, style="primary")]])

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

def spawn_emoji_task(bot_message: Message, custom_emoji: str = None, reply_markup=None):
    async def trigger():
        global emoji_index
        if not bot_message: return
        try:
            protect = await is_content_protected(bot_message.chat.id)
            if custom_emoji:
                await bot_message.reply(custom_emoji, reply_markup=reply_markup, protect_content=protect)
            else:
                async with emoji_lock:
                    selected = EMOJI_SEQUENCE[emoji_index]
                    emoji_index = (emoji_index + 1) % len(EMOJI_SEQUENCE)
                await bot_message.reply(selected, reply_markup=reply_markup, protect_content=protect)
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

async def live_typing_reply(message: Message, full_text: str, reply_markup=None, trigger_emoji_logic: bool = False) -> Message:
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
    protect = await is_content_protected(message.chat.id)
    
    for step in range(max_chunks):
        for line_idx, chunks in enumerate(chunked_lines):
            if step < len(chunks):
                if current_lines[line_idx]: current_lines[line_idx] += " " + chunks[step]
                else: current_lines[line_idx] = chunks[step]
                    
        visible_text = "\n".join([line for line in current_lines if line])
        if not visible_text.strip(): continue
            
        if sent_msg is None:
            sent_msg = await message.reply(visible_text, protect_content=protect)
            modification_count = 0
        else:
            try:
                await sent_msg.edit_text(visible_text)
                modification_count += 1
            except Exception:
                pass
                
        if trigger_emoji_logic and modification_count == 1:
            spawn_emoji_task(sent_msg)
            trigger_emoji_logic = False
            
        await asyncio.sleep(0.3)
        
    if reply_markup and sent_msg:
        try: await sent_msg.edit_reply_markup(reply_markup=reply_markup)
        except Exception: pass
            
    if sent_msg:
        if trigger_emoji_logic:
            spawn_emoji_task(sent_msg)
        bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
        asyncio.create_task(delayed_react(message.chat.id, sent_msg.message_id, bot_emoji))
        
    return sent_msg

async def extract_and_download(target: str, no_audio: bool = False):
    loop = asyncio.get_event_loop()
    fmt = 'bestvideo' if no_audio else 'bestvideo+bestaudio/best'
    ydl_opts = {'format': fmt, 'outtmpl': '%(uploader)s_tmp.%(ext)s', 'noplaylist': True, 'quiet': True}
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
        protect = await is_content_protected(message.chat.id)
        
        async with aiosqlite.connect("bot_data.db") as db:
            async with db.execute("SELECT file_id, media_type, title FROM media_cache WHERE media_key = ?", (cache_key,)) as cursor:
                cached_row = await cursor.fetchone()
                
        dynamic_kb = await get_dynamic_media_keyboard(user_id)
        if cached_row:
            file_id, media_type, title = cached_row
            if media_type == "album":
                file_ids = file_id.split(",")
                chunks = [file_ids[i:i + 8] for i in range(0, len(file_ids), 8)]
                for chunk in chunks:
                    media_group = [InputMediaDocument(media=fid) for fid in chunk]
                    album_msgs = await message.reply_media_group(media=media_group, protect_content=protect)
                    await asyncio.sleep(0.5)
                if album_msgs:
                    spawn_emoji_task(album_msgs[0])
                    bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                    asyncio.create_task(delayed_react(message.chat.id, album_msgs[0].message_id, bot_emoji))
            else:
                video_msg = await message.reply_document(document=file_id, caption="وهذا هوة الفيديو كدامك بالكامل\nالمايعرفني يعرفني شكد قوي", reply_markup=dynamic_kb, protect_content=protect)
                spawn_emoji_task(video_msg)
                bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                asyncio.create_task(delayed_react(message.chat.id, video_msg.message_id, bot_emoji))
            download_queue.task_done()
            continue

        status_msg = await live_typing_reply(message, "يتم العثور والبدء ب استكشاف طلبك\nسيتم ارسال الميديا الان", reply_markup=dynamic_kb, trigger_emoji_logic=True)
        file_path = None
        is_img_type = False
        
        try:
            res = await extract_and_download(target)
            if res and res[0]:
                file_path, orig_title, uploader, media_id, is_img_type, actual_ext = res
                
                if is_img_type:
                    if isinstance(file_path, list):
                        chunks = [file_path[i:i + 8] for i in range(0, len(file_path), 8)]
                        all_collected_ids = []
                        last_sent_group = None
                        
                        for chunk in chunks:
                            media_group = [InputMediaDocument(media=FSInputFile(fp)) for fp in chunk]
                            album_msgs = await message.reply_media_group(media=media_group, protect_content=protect)
                            if album_msgs:
                                last_sent_group = album_msgs
                                for m in album_msgs:
                                    if m.document:
                                        all_collected_ids.append(m.document.file_id)
                            await asyncio.sleep(0.5)
                        
                        if last_sent_group:
                            spawn_emoji_task(last_sent_group[0])
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
                    rand_suffix = "".join([str(random.randint(0, 9)) for _ in range(9)])
                    clean_uploader = ""
                    if uploader:
                        clean_uploader = re.sub(r'[^\w\-]', '', uploader).strip()
                    
                    if clean_uploader:
                        new_file_path = f"{clean_uploader}{rand_suffix}{actual_ext}"
                    else:
                        new_file_path = f"{rand_suffix}{actual_ext}"
                        
                    try: os.rename(file_path, new_file_path); file_path = new_file_path
                    except Exception: pass

                    video_msg = await message.reply_document(document=FSInputFile(file_path), caption="وهذا هوة الفيديو كدامك بالكامل\nالمايعرفني يعرفني شكد قوي", reply_markup=dynamic_kb, protect_content=protect)
                    spawn_emoji_task(video_msg)
                    if video_msg and video_msg.document:
                        async with aiosqlite.connect("bot_data.db") as db:
                            await db.execute("INSERT OR REPLACE INTO media_cache (media_key, file_id, media_type, title) VALUES (?, ?, ?, ?)", (cache_key, video_msg.document.file_id, "video", orig_title))
                            await db.commit()
                    bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                    asyncio.create_task(delayed_react(message.chat.id, video_msg.message_id, bot_emoji))
            else:
                if status_msg: await status_msg.delete()
                err_msg = await live_typing_reply(message, "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي", reply_markup=dynamic_kb, trigger_emoji_logic=True)
        except Exception:
            if status_msg: await status_msg.delete()
            err_msg = await live_typing_reply(message, "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي", reply_markup=dynamic_kb, trigger_emoji_logic=True)
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
    if welcome_state:
        kb_primary = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="المطور", url="tg://user?id=8597653867", style="primary")]])
        await live_typing_reply(message, "اهلين وياك بوت MediA تريد اشتغل دز\nرابط الفيديو التريده", reply_markup=kb_primary, trigger_emoji_logic=True)
        welcome_state = False
    else:
        await live_typing_reply(message, "مو ناوي تستعملني وتشغلني مثل البوتات ؟!\nاضوج ترى ازعل واصيح المولاي يهينك", reply_markup=None, trigger_emoji_logic=True)
        welcome_state = True

@dp.message(F.text == "ادت")
async def admin_cmd(message: Message):
    if is_all_admins(message.from_user.id):
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الزر")],
            [KeyboardButton(text="الغاء")]
        ], resize_keyboard=True)
        resp = await message.reply("تريد عرض رابط الزر دوس عرض الزر\nتريد تعين رابط الزر دوس تعيين الرابط", reply_markup=kb)
        spawn_emoji_task(resp)
    else:
        is_group = message.chat.type in ["group", "supergroup"]
        if not is_group:
            await handle_random_replies(message)

@dp.callback_query(F.data.startswith("show_cmds:"))
async def show_commands_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    creator_id = int(callback.data.split(":")[1])
    
    if user_id != creator_id:
        await callback.answer("شكد طفل وشكد منيوج نعلعلا ابوك\nونعلعلا نيج امك ياسكط", show_alert=True)
        return

    cmds_text = (
        "قفل / فتح النقل\n"
        "قفل / فتح الاشعارات\n"
        "رفع / تنزيل مطور بالرد او بالايدي\n"
        "مط / تن بالرد او بالايدي"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="عودة", callback_data=f"back_main:{creator_id}", style="success")]
    ])
    try:
        await callback.message.edit_text(text=cmds_text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer(cache_time=0)

@dp.callback_query(F.data.startswith("back_main:"))
async def back_main_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    creator_id = int(callback.data.split(":")[1])
    
    if user_id != creator_id:
        await callback.answer("شكد طفل وشكد منيوج نعلعلا ابوك\nونعلعلا نيج امك ياسكط", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="قفل / فتح", callback_data=f"show_cmds:{creator_id}", style="primary")],
        [InlineKeyboardButton(text="مسح", callback_data=f"delete_panel:{creator_id}", style="danger")]
    ])
    try:
        await callback.message.edit_text(text="الاوامر", reply_markup=kb)
    except Exception:
        pass
    await callback.answer(cache_time=0)

@dp.callback_query(F.data.startswith("delete_panel:"))
async def delete_panel_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
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
async def universal_handler(message: Message):
    global welcome_state, dynamic_admins
    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id
    is_group = message.chat.type in ["group", "supergroup"]
    is_channel = message.chat.type == "channel"
    protect = await is_content_protected(chat_id)

    cmd_cleaned = message.text.strip() if message.text else ""

    if user_id in PRIMARY_ADMINS and cmd_cleaned:
        target_user_id = None
        is_promote_cmd = False
        is_demote_cmd = False

        if cmd_cleaned.startswith("رفع مطور ") or cmd_cleaned.startswith("مط "):
            is_promote_cmd = True
            parts = cmd_cleaned.split()
            if len(parts) >= 2:
                potential_id = parts[-1]
                if potential_id.isdigit():
                    target_user_id = int(potential_id)
        elif cmd_cleaned in ["رفع مطور", "مط"]:
            if message.reply_to_message and message.reply_to_message.from_user:
                is_promote_cmd = True
                target_user_id = message.reply_to_message.from_user.id

        if cmd_cleaned.startswith("تنزيل مطور ") or cmd_cleaned.startswith("تن "):
            is_demote_cmd = True
            parts = cmd_cleaned.split()
            if len(parts) >= 2:
                potential_id = parts[-1]
                if potential_id.isdigit():
                    target_user_id = int(potential_id)
        elif cmd_cleaned in ["تنزيل مطور", "تن"]:
            if message.reply_to_message and message.reply_to_message.from_user:
                is_demote_cmd = True
                target_user_id = message.reply_to_message.from_user.id

        if is_promote_cmd and target_user_id:
            if target_user_id in PRIMARY_ADMINS or target_user_id in dynamic_admins:
                reply_txt = "¹# - هذا مطور اصلا بعد كلبي\nوين ارفعه بعد"
                resp = await message.reply(reply_txt, protect_content=protect)
                spawn_emoji_task(resp)
                return
            
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR REPLACE INTO dynamic_admins (user_id) VALUES (?)", (target_user_id,))
                await db.commit()
            dynamic_admins.add(target_user_id)
            reply_txt = f"¹# - تم رفعه مطور مولاي\nيدلل تاج راسي"
            resp = await message.reply(reply_txt, protect_content=protect)
            spawn_emoji_task(resp)
            return
        elif is_promote_cmd:
            return

        if is_demote_cmd and target_user_id:
            if target_user_id not in dynamic_admins and target_user_id not in PRIMARY_ADMINS:
                reply_txt = "¹# - هذا مو مطور اصلا بعد كلبي\nمنين انزله بعد"
                resp = await message.reply(reply_txt, protect_content=protect)
                spawn_emoji_task(resp)
                return
            
            if target_user_id in PRIMARY_ADMINS:
                return
                
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("DELETE FROM dynamic_admins WHERE user_id = ?", (target_user_id,))
                await db.commit()
            dynamic_admins.discard(target_user_id)
            reply_txt = f"¹# - تم تنزيله من المطورين مولاي\nيدلل تاج راسي"
            resp = await message.reply(reply_txt, protect_content=protect)
            spawn_emoji_task(resp)
            return
        elif is_demote_cmd:
            return

    if message.reply_to_message and cmd_cleaned == "ستيكر":
        if is_group and await is_user_admin_or_owner(chat_id, user_id):
            rep = message.reply_to_message
            target_file_id = None
            if rep.video:
                target_file_id = rep.video.file_id
            elif rep.document and rep.document.mime_type and rep.document.mime_type.startswith("video/"):
                target_file_id = rep.document.file_id
            
            if target_file_id:
                user_emoji = get_smart_reaction(last_user_reaction, chat_id)
                asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))
                
                try:
                    file_info = await bot.get_file(target_file_id)
                    direct_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
                    
                    res = await extract_and_download(direct_url, no_audio=True)
                    if res and res[0] and not res[4]:
                        file_path = res[0]
                        dynamic_kb = await get_dynamic_media_keyboard(user_id)
                        gif_msg = await message.reply_animation(animation=FSInputFile(file_path), reply_markup=dynamic_kb, has_spoiler=True, protect_content=protect)
                        spawn_emoji_task(gif_msg)
                        
                        bot_emoji = get_smart_reaction(last_bot_reaction, chat_id)
                        asyncio.create_task(delayed_react(chat_id, gif_msg.message_id, bot_emoji))
                        
                        try: os.remove(file_path)
                        except Exception: pass
                except Exception:
                    pass
                return
        else:
            if not is_group and not is_channel:
                await handle_random_replies(message)
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

    if cmd_cleaned == "الاوامر":
        if is_all_admins(user_id) or (is_group and await is_user_owner(chat_id, user_id)) or (not is_group and not is_channel):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="قفل / فتح", callback_data=f"show_cmds:{user_id}", style="primary")],
                [InlineKeyboardButton(text="مسح", callback_data=f"delete_panel:{user_id}", style="danger")]
            ])
            resp = await message.reply("الاوامر", reply_markup=kb, protect_content=protect)
            spawn_emoji_task(resp)
        else:
            if not is_group and not is_channel:
                await handle_random_replies(message)
        return

    if cmd_cleaned in ["قفل الاشعارات", "فتح الاشعارات"]:
        if is_group or is_channel:
            if is_all_admins(user_id) or await is_user_owner(chat_id, user_id):
                status_to_set = "locked" if cmd_cleaned == "قفل الاشعارات" else "unlocked"
                async with aiosqlite.connect("bot_data.db") as db:
                    await db.execute("INSERT OR REPLACE INTO chat_notifications (chat_id, status) VALUES (?, ?)", (chat_id, status_to_set))
                    await db.commit()
                
                action_word = "قفل" if status_to_set == "locked" else "فتح"
                reply_txt = f"¹# - تم {action_word} الاشعارات مولاي\nيدلل تاج راسي"
                
                resp = await message.reply(reply_txt, protect_content=protect)
                spawn_emoji_task(resp)
        else:
            await handle_random_replies(message)
        return

    if cmd_cleaned in ["قفل النقل", "فتح النقل"]:
        if is_all_admins(user_id) or (is_group and await is_user_owner(chat_id, user_id)) or (not is_group and not is_channel):
            status_to_set = "locked" if cmd_cleaned == "قفل النقل" else "unlocked"
            async with aiosqlite.connect("bot_data.db") as db:
                await db.execute("INSERT OR REPLACE INTO chat_protection (chat_id, status) VALUES (?, ?)", (chat_id, status_to_set))
                await db.commit()
            
            action_word = "قفل" if status_to_set == "locked" else "فتح"
            reply_txt = f"¹# - تم {action_word} النقل مولاي\nيدلل تاج راسي"
            
            new_protect = (status_to_set == "locked")
            resp = await message.reply(reply_txt, protect_content=new_protect)
            spawn_emoji_task(resp)
        return

    if cmd_cleaned in ["تعيين الرابط", "عرض الزر"] and not is_group and not is_channel:
        if is_all_admins(user_id):
            if cmd_cleaned == "تعيين الرابط":
                admin_states[user_id] = "waiting_link"
                kb_back = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="عودة")]], resize_keyboard=True)
                resp = await message.reply("ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", reply_markup=kb_back, protect_content=protect)
                spawn_emoji_task(resp)
            elif cmd_cleaned == "عرض الزر":
                kb_second_page = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="عودة")]], resize_keyboard=True)
                dynamic_kb = await get_dynamic_media_keyboard(user_id)
                resp = await bot.send_message(
                    chat_id=chat_id,
                    text="هيج صار الزر بعد عيني دوس وشوف الرابط\nيشتغل لو لا",
                    reply_markup=dynamic_kb,
                    reply_to_message_id=message.message_id,
                    protect_content=protect
                )
                spawn_emoji_task(resp, reply_markup=kb_second_page)
            return

    if cmd_cleaned == "الغاء" and not is_group and not is_channel:
        if is_all_admins(user_id):
            admin_states.pop(user_id, None)
            resp = await message.reply("صار وتدلل\nمنو يكدر يعصيك يبعد كسي اه", reply_markup=ReplyKeyboardRemove(), protect_content=protect)
            spawn_emoji_task(resp)
            return

    if cmd_cleaned == "عودة" and not is_group and not is_channel:
        if is_all_admins(user_id):
            admin_states.pop(user_id, None)
            kb_orig = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الزر")],
                [KeyboardButton(text="الغاء")]
            ], resize_keyboard=True)
            spawn_emoji_task(message, reply_markup=kb_orig)
            return

    if not is_group and not is_channel and is_all_admins(user_id) and admin_states.get(user_id) == "waiting_link":
        admin_states.pop(user_id, None)
        kb_orig = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الزر")],
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
                await set_setting("btn_style", "primary")
                resp = await message.reply("تم تعيين زر الاشتراك العلني مثل ماردت\nسمعا وطاعة العيرك", reply_markup=kb_orig, protect_content=protect)
            else:
                resp = await message.reply("اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي", reply_markup=kb_orig, protect_content=protect)
        else:
            resp = await message.reply("اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي", reply_markup=kb_orig, protect_content=protect)
        spawn_emoji_task(resp)
        return

    if message.text and message.text != "ادت" and message.text not in ["تعيين الرابط", "عرض الزر", "الغاء", "عودة", "قفل النقل", "فتح النقل", "قفل الاشعارات", "فتح الاشعارات", "الاوامر"]:
        if is_group and await is_user_admin_or_owner(chat_id, user_id):
            user_emoji = get_smart_reaction(last_user_reaction, chat_id)
            asyncio.create_task(delayed_react(chat_id, message.message_id, user_emoji))

    content_text = message.text if message.text else (message.caption if message.caption else "")
    all_urls = ANY_URL_REGEX.findall(content_text)
    downloadable_urls = [url for url in all_urls if "t.me" not in url and "telegram.me" not in url]
    
    if downloadable_urls:
        if is_group and not await is_user_admin_or_owner(chat_id, user_id):
            return
        if not await check_force_subscription(user_id):
            force_kb = await get_force_sub_keyboard()
            await live_typing_reply(message, "اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني", reply_markup=force_kb, trigger_emoji_logic=True)
            return
            
        async with counter_lock:
            current_count = user_task_counts.get(user_id, 0)
            for url in downloadable_urls:
                if current_count >= 7: break
                current_count += 1; user_task_counts[user_id] = current_count
                await download_queue.put((message, url, user_id, f"media_{url}"))
        return

    if content_text.strip() in ["ادت", "تعيين الرابط", "عرض الزر", "الغاء", "عودة", "قفل النقل", "فتح النقل", "قفل الاشعارات", "فتح الاشعارات", "الاوامر", "رفع مطور", "تنزيل مطور", "مط", "تن"] or content_text.strip().startswith(("رفع مطور ", "تنزيل مطور ", "مط ", "تن ")):
        return

    if is_group:
        if content_text.strip() == "بوت":
            if await is_user_admin_or_owner(chat_id, user_id, force_update=True):
                await handle_random_replies(message)
    elif not is_channel:
        await handle_random_replies(message)

async def send_startup_notification():
    for admin_id in PRIMARY_ADMINS:
        try:
            protect = await is_content_protected(admin_id)
            msg = await bot.send_message(chat_id=admin_id, text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!", protect_content=protect)
            spawn_emoji_task(msg, custom_emoji="🧨")
        except Exception:
            pass

async def main():
    await init_db()
    asyncio.create_task(queue_worker())
    asyncio.create_task(send_startup_notification())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
