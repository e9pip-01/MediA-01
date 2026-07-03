import os
import re
import asyncio
import random
import time
import sqlite3
import aiohttp
import aiofiles
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import yt_dlp

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

TOKEN = os.getenv("TELEGRAM_TOKEN")
DEV_ID = 8597653867

DEFAULT_CHANNEL = "tg://user?id=3454506837"
channel_link = ""
button_name_1 = "رب العالمين"
button_name_2 = "سلوى وبس"
subscribe_btn_name = "اشترك بالقناة"
REACTIONS = ["😘", "😡", "🥰", "🍓", "😭", "🤗", "🤣"]

last_reactions = {}
bot_audio_messages = {}

router = Router()

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            chat_state INTEGER DEFAULT 0,
            action TEXT DEFAULT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            cache_key TEXT PRIMARY KEY,
            file_id TEXT,
            title TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_state(user_id: int) -> dict:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT chat_state, action FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"chat_state": row[0], "action": row[1]}
    return {"chat_state": 0, "action": None}

def update_user_state(user_id: int, chat_state: int, action: str = None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, chat_state, action)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET chat_state = ?, action = ?
    """, (user_id, chat_state, action, chat_state, action))
    conn.commit()
    conn.close()

def get_cached_song(cache_key: str) -> dict:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, title FROM cache WHERE cache_key = ?", (cache_key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"file_id": row[0], "title": row[1]}
    return None

def set_cached_song(cache_key: str, file_id: str, title: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cache (cache_key, file_id, title)
        VALUES (?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET file_id = ?, title = ?
    """, (cache_key, file_id, title, file_id, title))
    conn.commit()
    conn.close()

def get_attached_buttons():
    keyboard = [
        [InlineKeyboardButton(text=button_name_1, url="tg://user?id=8597653867", style="destructive")],
        [InlineKeyboardButton(text=button_name_2, url="tg://user?id=3454506837", style="primary")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscribe_button():
    target_url = channel_link.strip() if channel_link else DEFAULT_CHANNEL
    if not (target_url.startswith("http://") or target_url.startswith("https://") or target_url.startswith("tg://")):
        target_url = f"https://t.me/{target_url.replace('@', '')}"
    
    keyboard = [
        [InlineKeyboardButton(text=subscribe_btn_name, url=target_url, style="destructive")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def filter_title(title: str) -> str:
    res = []
    latin_upper = {'a', 'u', 'n', 'm', 'g', 't', 'f', 'j'}
    cyrillic_upper = {'а', 'б', 'и'}
    
    for char in title:
        lower_char = char.lower()
        if lower_char in latin_upper or lower_char in cyrillic_upper:
            res.append(lower_char.upper())
        else:
            res.append(lower_char)
            
    return "".join(res)

async def check_subscription(bot: Bot, user_id: int) -> bool:
    if user_id == DEV_ID:
        return True
    
    target_url = channel_link.strip() if channel_link else DEFAULT_CHANNEL
    chat_target = target_url.replace("https://t.me/", "@").replace("http://t.me/", "@")
    if "tg://user?id=" in chat_target:
        return True
        
    try:
        member = await bot.get_chat_member(chat_id=chat_target, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except:
        return True

async def add_banana_reaction(message: Message):
    await asyncio.sleep(1.5)
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "🍌"}])
    except:
        pass

async def add_unique_reaction(message: Message):
    await asyncio.sleep(3)
    chat_id = message.chat.id
    used = last_reactions.get(chat_id, [])
    available = [r for r in REACTIONS if r not in used]
    
    if not available:
        available = REACTIONS.copy()
        used = []
        
    chosen = random.choice(available)
    used.append(chosen)
    if len(used) > 3:
        used.pop(0)
    last_reactions[chat_id] = used
    
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": chosen}])
    except:
        pass

async def send_animated_text(message: Message, full_text: str, reply_markup=None, is_emoji=False, trigger_early_emoji=True, attach_global_buttons=True, custom_inline_markup=None):
    if is_emoji and full_text == "🫦":
        msg = await message.reply(text="🫦", reply_markup=reply_markup)
        asyncio.create_task(add_unique_reaction(msg))
        return msg

    lines = full_text.split('\n')
    all_chunks = []
    
    for line in lines:
        words = line.split()
        if not words:
            all_chunks.append("")
            continue
        line_chunks = []
        i = 0
        take_three = True
        while i < len(words):
            size = 3 if take_three else 2
            line_chunks.append(" ".join(words[i:i+size]))
            i += size
            take_three = not take_three
        all_chunks.append(line_chunks)

    total_steps = max(len(chunks) for chunks in all_chunks if chunks)
    
    current_lines = []
    for chunks in all_chunks:
        if chunks:
            current_lines.append(chunks[0])
        else:
            current_lines.append("")
            
    current_text = "\n".join(current_lines)
    base_msg = await message.reply(text=current_text, reply_markup=None)
    asyncio.create_task(add_unique_reaction(base_msg))

    emoji_triggered = False

    for step in range(1, total_steps):
        await asyncio.sleep(0.3)
        current_lines = []
        for chunks in all_chunks:
            if not chunks:
                current_lines.append("")
            else:
                step_index = min(step, len(chunks) - 1)
                current_lines.append(" ".join(chunks[:step_index + 1]))
        
        current_text = "\n".join(current_lines)
        
        try:
            await base_msg.edit_text(text=current_text, reply_markup=None)
        except:
            pass

        if trigger_early_emoji and not emoji_triggered:
            asyncio.create_task(send_animated_text(message, "🫦", is_emoji=True, reply_markup=None, attach_global_buttons=False, custom_inline_markup=None))
            emoji_triggered = True
            
    if trigger_early_emoji and not emoji_triggered:
        asyncio.create_task(send_animated_text(message, "🫦", is_emoji=True, reply_markup=None, attach_global_buttons=False, custom_inline_markup=None))

    if custom_inline_markup:
        final_markup = custom_inline_markup
    else:
        final_markup = get_attached_buttons() if attach_global_buttons else None

    try:
        await base_msg.edit_reply_markup(reply_markup=final_markup)
    except:
        pass

    return base_msg

async def send_dynamic_reply(message: Message):
    user_id = message.from_user.id
    current_state = get_user_state(user_id)
    state_val = current_state.get('chat_state', 0)
    
    if state_val == 0:
        await send_animated_text(message, "تفضل\nكول يوت ثم اذكر اسم الاغنيه وراح توصلك", trigger_early_emoji=True)
        update_user_state(user_id, chat_state=1, action=current_state.get('action'))
    else:
        await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك", trigger_early_emoji=True)
        update_user_state(user_id, chat_state=0, action=current_state.get('action'))

def make_progress_hook(loop, bot, chat_id, message_id):
    state = {
        'last_update_time': 0,
        'last_percent': 0
    }
    
    def hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            if total:
                percent_num = int(downloaded / total * 100)
                now = time.time()
                
                step = 10 if state['last_percent'] >= 80 else 15
                
                if percent_num >= state['last_percent'] + step or percent_num == 100 or (now - state['last_update_time'] >= 2.0):
                    if percent_num != state['last_percent']:
                        state['last_percent'] = percent_num
                        state['last_update_time'] = now
                        
                        text = f"يتم العثور على الاغنيه مولاي\nماتنتظر فدوا {percent_num}%"
                        asyncio.run_coroutine_threadsafe(
                            bot.edit_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=None),
                            loop
                        )
    return hook

def download_video_sync(ydl_opts, target_input):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(target_input, download=True)
        video_info = info['entries'][0] if 'entries' in info else info
        filename = ydl.prepare_filename(video_info)
        return filename

async def process_youtube_download(message: Message, target_input: str, cache_key: str):
    chat_id = message.chat.id
    cached_song = get_cached_song(cache_key)

    if cached_song:
        try:
            cached_file_id = cached_song["file_id"]
            cached_title = cached_song["title"]
            
            audio_msg = await message.reply_document(
                document=cached_file_id,
                caption=cached_title,
                reply_markup=get_attached_buttons()
            )
            asyncio.create_task(add_unique_reaction(audio_msg))
            
            if chat_id not in bot_audio_messages:
                bot_audio_messages[chat_id] = []
            bot_audio_messages[chat_id].append(audio_msg.message_id)
            return
        except:
            pass

    status_message = await send_animated_text(message, "يتم العثور على الاغنيه مولاي\nماتنتظر فدوا", attach_global_buttons=False, trigger_early_emoji=True)

    loop = asyncio.get_running_loop()
    progress_hook = make_progress_hook(loop, message.bot, chat_id, status_message.message_id)

    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'quiet': True,
        'socket_timeout': 15,
        'nocheckcertificate': True,
        'user_agent': user_agent,
        'http_chunk_size': 1048576,
        'external_downloader': 'curl_cffi',
        'external_downloader_args': ['--impersonate', 'chrome'],
        'http_headers': {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Ch-Ua': '"Google Chrome";v="150", "Not=A?Brand";v="8", "Chromium";v="150"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
        },
        'progress_hooks': [progress_hook],
    }
    
    audio_filename = None
    
    try:
        audio_filename = await loop.run_in_executor(None, download_video_sync, ydl_opts, target_input)
        
        base_name, original_ext = os.path.splitext(os.path.basename(audio_filename))
        filtered_title = filter_title(base_name)
        
        final_filename = f"{filtered_title}{original_ext}"
        if os.path.exists(audio_filename):
            os.rename(audio_filename, final_filename)
            audio_filename = final_filename

        async with aiofiles.open(audio_filename, 'rb') as f:
            audio_data = await f.read()

        from aiogram.types import BufferedInputFile
        input_file = BufferedInputFile(audio_data, filename=os.path.basename(audio_filename))

        audio_msg = await message.reply_document(
            document=input_file, 
            caption=filtered_title,
            reply_markup=get_attached_buttons()
        )
        asyncio.create_task(add_unique_reaction(audio_msg))
        
        set_cached_song(cache_key, audio_msg.document.file_id, filtered_title)
        
        if chat_id not in bot_audio_messages:
            bot_audio_messages[chat_id] = []
        bot_audio_messages[chat_id].append(audio_msg.message_id)
        
        await status_message.delete()

    except Exception as e:
        try:
            await status_message.delete()
        except:
            pass

        await send_animated_text(message, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي", trigger_early_emoji=True)
        
    finally:
        if audio_filename and os.path.exists(audio_filename):
            try:
                os.remove(audio_filename)
            except:
                pass

@router.callback_query(F.data.startswith("btn_"))
async def handle_callback_buttons(callback: CallbackQuery):
    await callback.answer()

@router.message(F.text)
async def handle_message(message: Message):
    global channel_link, button_name_1, button_name_2, subscribe_btn_name
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()
    is_group = message.chat.type in ['group', 'supergroup']
    is_private = message.chat.type == 'private'
    
    is_admin_or_dev = False
    if user_id == DEV_ID:
        is_admin_or_dev = True
    elif is_group:
        try:
            member = await message.chat.get_member(user_id)
            if member.status in ['administrator', 'creator']:
                is_admin_or_dev = True
        except:
            pass

    current_user_state = get_user_state(user_id)
    current_action = current_user_state.get('action')

    if user_id != DEV_ID:
        is_subscribed = await check_subscription(message.bot, user_id)
        if not is_subscribed:
            await send_animated_text(
                message=message,
                full_text="اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني",
                reply_markup=None,
                trigger_early_emoji=True,
                attach_global_buttons=False,
                custom_inline_markup=get_subscribe_button()
            )
            return

    is_youtube_url = False
    extracted_url = None
    url_match = re.search(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s]+)', text)
    if url_match:
        is_youtube_url = True
        extracted_url = url_match.group(1)

    is_yut_command = bool(re.match(r'^يوت\s+(.+)$', text))
    is_audio_request = is_yut_command or is_youtube_url

    if is_audio_request:
        if is_private or (is_group and is_admin_or_dev):
            asyncio.create_task(add_banana_reaction(message))
    else:
        if is_private:
            asyncio.create_task(add_unique_reaction(message))
        elif is_group and is_admin_or_dev:
            asyncio.create_task(add_unique_reaction(message))
    
    if is_private and user_id == DEV_ID and text == "الغاء":
        update_user_state(user_id, chat_state=0, action=None)
        await send_animated_text(message, "صار دادي ماراح اغير او اسوي شي\nءمهمواح", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
        return

    if is_private and user_id == DEV_ID and current_action == 'wait_link':
        channel_link = text
        await send_animated_text(message, "تم تعيين زر الاشتراك العلني تدلل\nءمهمواح", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
        update_user_state(user_id, chat_state=0, action=None)
        return

    elif is_private and user_id == DEV_ID and current_action in ['wait_name_btn1', 'wait_name_btn2', 'wait_name_sub']:
        words = text.split()
        if len(words) <= 3:
            if current_action == 'wait_name_btn1':
                button_name_1 = text
            elif current_action == 'wait_name_btn2':
                button_name_2 = text
            elif current_action == 'wait_name_sub':
                subscribe_btn_name = text
            await send_animated_text(message, "غيرت الاسم بدون مشاكل يبعدي انه\nغير يدلل مولاي", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
            update_user_state(user_id, chat_state=0, action=None)
        else:
            await send_animated_text(message, "الاسم اطول من المسموح به ثلاث كلمات\nك اقصى طول", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
            update_user_state(user_id, chat_state=0, action=None)
        return

    if text == "تنظيف":
        if is_admin_or_dev:
            messages_to_clean = bot_audio_messages.get(chat_id, [])
            deleted_count = 0
            
            for msg_id in messages_to_clean:
                try:
                    await message.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    deleted_count += 1
                except:
                    pass
                    
            bot_audio_messages[chat_id] = []
            await send_animated_text(message, f"تم مسح {deleted_count} من الصوتيات\nلان امرتني مولاي", trigger_early_emoji=True, attach_global_buttons=False)
        return

    if is_private and user_id == DEV_ID and text == "ادت":
        keyboard = [
            [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الاشتراك")],
            [KeyboardButton(text="تغيير اسم الزر")],
            [KeyboardButton(text="الغاء")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await send_animated_text(
            message=message,
            full_text="تريد تغير اسم الزر دوس تغيير اسم الزر\nتريد تعين رابط الزر دوس تعيين الرابط",
            reply_markup=reply_markup,
            trigger_early_emoji=True,
            attach_global_buttons=False
        )
        return

    if is_private and user_id == DEV_ID:
        if text == "عرض الاشتراك":
            await send_animated_text(
                message=message,
                full_text="اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني",
                reply_markup=ReplyKeyboardRemove(),
                trigger_early_emoji=True,
                attach_global_buttons=False,
                custom_inline_markup=get_subscribe_button()
            )
            return

        elif text == "تعيين الرابط":
            update_user_state(user_id, chat_state=current_user_state.get('chat_state', 0), action='wait_link')
            await send_animated_text(message, "ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
            return
            
        elif text == "تغيير اسم الزر":
            sub_keyboard = [
                [KeyboardButton(text="رب العالمين"), KeyboardButton(text="سلوى وبس")],
                [KeyboardButton(text=subscribe_btn_name), KeyboardButton(text="الغاء")]
            ]
            sub_reply_markup = ReplyKeyboardMarkup(keyboard=sub_keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            await send_animated_text(
                message=message,
                full_text="اسماء الازرار مكتوبات يم الكيبورد\nيا زر تريد تبدل اسمه بدله",
                reply_markup=sub_reply_markup,
                trigger_early_emoji=True,
                attach_global_buttons=False
            )
            return

        elif text == "رب العالمين" and current_action is None:
            update_user_state(user_id, chat_state=current_user_state.get('chat_state', 0), action='wait_name_btn1')
            await send_animated_text(message, "شتريد اسم الزر المرفق وي الرسايل\nيصير تاج راسي", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
            return

        elif text == "سلوى وبس" and current_action is None:
            update_user_state(user_id, chat_state=current_user_state.get('chat_state', 0), action='wait_name_btn2')
            await send_animated_text(message, "شتريد اسم الزر المرفق وي الرسايل\nيصير تاج راسي", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
            return

        elif text == subscribe_btn_name and current_action is None:
            update_user_state(user_id, chat_state=current_user_state.get('chat_state', 0), action='wait_name_sub')
            await send_animated_text(message, "شتريد اسم الزر المرفق وي الرسايل\nيصير تاج راسي", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True, attach_global_buttons=False)
            return

    if is_youtube_url:
        await process_youtube_download(message, extracted_url, extracted_url)
        return

    if is_yut_command:
        match = re.match(r'^يوت\s+(.+)$', text)
        if match:
            search_query = match.group(1).strip().lower()
            cached_song = get_cached_song(search_query)
            if cached_song:
                await process_youtube_download(message, None, search_query)
            else:
                yt_search_query = f"ytsearch1:{search_query}"
                await process_youtube_download(message, yt_search_query, search_query)
        return

    if is_group:
        if text == "بوت":
            await send_dynamic_reply(message)
        return

    if is_private:
        await send_dynamic_reply(message)

async def main():
    if not TOKEN:
        return

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
