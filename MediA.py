import os
import re
import asyncio
import random
import aiosqlite
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import yt_dlp

class BotMessages:
    RESP_1 = "اهلين وياك بوت MUsic تريد اشتغل\nدز لو رابط لو يوت وكول عنوان اغنيتك"
    RESP_2 = "مو ناوي تستعملني عدل?! تريد اضوج\nترى ازعل واصيح المولاي يهينك"
    
    PROCESSING = "يتم العثور والبدء ب استكشاف طلبك\nسيتم تنفيذه الان"
    NOT_FOUND = "الرابط غير مدعوم او العنوان لم يتم العثور\nعليه عزيزي"
    SUCCESS = "وهايهية اغنيتك تاج راسي شتريد بعد\nتدلل بعدقلبي"
    
    ADMIN_MENU = "تريد تغير اسم الزر دوس تغيير اسم الزر\nتريد تعين رابط الزر دوس تعيين الرابط"
    ASK_LINK = "ارسل يوزر / رابط القناة او الكروب\nيلا مولاي"
    BAD_LINK = "اهو لاتمضرط وياي مو راح اضوج\nهوف منك مولاي"
    SET_SUCCESS = "تم تعيين زر الاشتراك العلني مثل ماردت\nسمعا وطاعة العيرك"
    PREVIEW_MSG = "هيج صار الزر بعد عيني دوس وشوف الرابط\nيشتغل لو لا"
    CANCEL_MSG = "صار وتدلل\nمنو يكدر يعصيك يبعد كسي اه"

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

download_queue = asyncio.Queue()

user_task_counts = {}
counter_lock = asyncio.Lock()

welcome_state = True
active_emoji_tasks = []

ADMIN_IDS = [8597653867, 8467593882]

SUBSCRIBE_LINK = "tg://user?id=8597653867"
BUTTON_TEXT = "رب العالمين"
BUTTON_STYLE = "primary"

admin_states = {}

REACTIONS_POOL = ["🥰", "😡", "😘", "🍓", "🤣", "🤗", "😭"]
last_user_reaction = {}
last_bot_reaction = {}

YOUTUBE_REGEX = re.compile(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11})')
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
        await db.commit()

def format_english_title(title: str) -> str:
    lowered = title.lower()
    formatted = re.sub(r'[atnmgfujl]', lambda m: m.group(0).upper(), lowered)
    return formatted

def get_clean_url(input_str: str) -> str:
    input_str = input_str.strip()
    if input_str.startswith("@"):
        return f"https://t.me/{input_str[1:]}"
    elif input_str.startswith("http://") or input_str.startswith("https://"):
        return input_str
    elif input_str.startswith("t.me/"):
        return f"https://{input_str}"
    else:
        return f"https://t.me/{input_str}"

def get_sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=BUTTON_TEXT, url=SUBSCRIBE_LINK, style=BUTTON_STYLE)]
    ])

def get_smart_reaction(last_reaction_dict, key: int) -> str:
    last = last_reaction_dict.get(key)
    available = [r for r in REACTIONS_POOL if r != last]
    chosen = random.choice(available)
    last_reaction_dict[key] = chosen
    return chosen

async def delayed_react(chat_id: int, message_id: int, emoji: str, delay: float = None):
    if delay is None:
        delay = random.choice([2.4, 3.6, 4.8])
    await asyncio.sleep(delay)
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[{"type": "emoji", "emoji": emoji}],
            is_big=False
        )
    except Exception:
        pass

async def is_user_admin_or_owner(chat_id: int, user_id: int, force_update: bool = False) -> bool:
    if user_id in ADMIN_IDS:
        return True
        
    current_time = time.time()
    
    if not force_update:
        async with aiosqlite.connect("bot_data.db") as db:
            async with db.execute(
                "SELECT is_admin, expires_at FROM permissions_cache WHERE chat_id = ? AND user_id = ?", 
                (chat_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    is_admin, expires_at = row
                    if current_time < expires_at:
                        return bool(is_admin)
            
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        res = member.status in ["administrator", "creator"]
    except Exception:
        res = False
        
    async with aiosqlite.connect("bot_data.db") as db:
        await db.execute("""
            INSERT OR REPLACE INTO permissions_cache (chat_id, user_id, is_admin, expires_at)
            VALUES (?, ?, ?, ?)
        """, (chat_id, user_id, int(res), current_time + 10.0))
        await db.commit()
        
    return res

async def live_typing_reply(message: Message, full_text: str, reply_markup=None) -> Message:
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
    
    for step in range(max_chunks):
        for line_idx, chunks in enumerate(chunked_lines):
            if step < len(chunks):
                if current_lines[line_idx]:
                    current_lines[line_idx] += " " + chunks[step]
                else:
                    current_lines[line_idx] = chunks[step]
                    
        visible_text = "\n".join([line for line in current_lines if line])
        
        if not visible_text.strip():
            continue
            
        if sent_msg is None:
            sent_msg = await message.reply(visible_text)
        else:
            try:
                await sent_msg.edit_text(visible_text)
            except Exception:
                pass
        await asyncio.sleep(0.3)
        
    if reply_markup and sent_msg:
        try:
            await sent_msg.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass
            
    if sent_msg:
        bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
        asyncio.create_task(delayed_react(message.chat.id, sent_msg.message_id, bot_emoji))
        
    return sent_msg

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

async def extract_and_download(target: str):
    loop = asyncio.get_event_loop()
    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': '%(title)s.%(ext)s', 'noplaylist': True, 'quiet': True}
    
    if not (target.startswith("http://") or target.startswith("https://")):
        search_target = f"ytsearch1:{target}"
    else:
        search_target = target

    def sync_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            if 'entries' in info:
                if not info['entries']:
                    return None, None
                info = info['entries'][0]
            
            raw_filename = ydl.prepare_filename(info)
            original_title = info.get('title', 'Audio')
            return raw_filename, original_title
            
    return await loop.run_in_executor(None, sync_download)

async def queue_worker():
    while True:
        message, target, user_id = await download_queue.get()
        status_msg = await live_typing_reply(message, BotMessages.PROCESSING, reply_markup=get_sub_keyboard())
        file_path = None
        try:
            file_path, orig_title = await extract_and_download(target)
            if file_path and os.path.exists(file_path):
                new_title = format_english_title(orig_title)
                base, ext = os.path.splitext(file_path)
                new_file_path = f"{new_title}{ext}"
                try:
                    os.rename(file_path, new_file_path)
                    file_path = new_file_path
                except Exception:
                    pass

                audio_msg = await message.reply_audio(
                    audio=FSInputFile(file_path), 
                    caption=BotMessages.SUCCESS, 
                    title=new_title,
                    reply_markup=get_sub_keyboard()
                )
                bot_emoji = get_smart_reaction(last_bot_reaction, message.chat.id)
                asyncio.create_task(delayed_react(message.chat.id, audio_msg.message_id, bot_emoji))
            else:
                if status_msg:
                    await status_msg.delete()
                await live_typing_reply(message, BotMessages.NOT_FOUND, reply_markup=get_sub_keyboard())
        except Exception:
            if status_msg:
                await status_msg.delete()
            await live_typing_reply(message, BotMessages.NOT_FOUND, reply_markup=get_sub_keyboard())
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
                    if user_task_counts[user_id] <= 0:
                        user_task_counts.pop(user_id, None)
                        
            download_queue.task_done()

@dp.message(F.text == "ادت")
async def admin_cmd(message: Message):
    if message.from_user.id in ADMIN_IDS:
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="تعيين رابط زر الاشتراك"), KeyboardButton(text="عرض الزر")]
        ], resize_keyboard=True)
        await message.reply(BotMessages.ADMIN_MENU, reply_markup=kb)
    else:
        is_group = message.chat.type in ["group", "supergroup"]
        if not is_group or (is_group and await is_user_admin_or_owner(message.chat.id, message.from_user.id, force_update=True)):
            bot_emoji = get_smart_reaction(last_user_reaction, message.chat.id)
            asyncio.create_task(delayed_react(message.chat.id, message.message_id, bot_emoji, delay=0.0))

@dp.message()
async def universal_handler(message: Message):
    global welcome_state, active_emoji_tasks, SUBSCRIBE_LINK, BUTTON_TEXT, BUTTON_STYLE
    
    user_id = message.from_user.id
    is_group = message.chat.type in ["group", "supergroup"]

    if message.text and message.text.strip() == "بوت":
        if not is_group or (is_group and await is_user_admin_or_owner(message.chat.id, user_id, force_update=True)):
            user_emoji = get_smart_reaction(last_user_reaction, message.chat.id)
            asyncio.create_task(delayed_react(message.chat.id, message.message_id, user_emoji))
            await handle_random_replies(message)
        return

    if message.text and message.text.strip() == "يوت":
        if not is_group or (is_group and await is_user_admin_or_owner(message.chat.id, user_id, force_update=True)):
            special_emoji = random.choice(["🌭", "🍌"])
            asyncio.create_task(delayed_react(message.chat.id, message.message_id, special_emoji, delay=0.0))
        return

    if message.text and message.text != "ادت" and message.text not in ["تعيين رابط زر الاشتراك", "عرض الزر", "إلغاء"] and message.text.strip() != "بوت" and message.text.strip() != "يوت":
        if not is_group or (is_group and await is_user_admin_or_owner(message.chat.id, user_id)):
            user_emoji = get_smart_reaction(last_user_reaction, message.chat.id)
            asyncio.create_task(delayed_react(message.chat.id, message.message_id, user_emoji))

    if message.text == "إلغاء" and user_id in ADMIN_IDS:
        admin_states.pop(user_id, None)
        await message.reply(BotMessages.CANCEL_MSG, reply_markup=ReplyKeyboardRemove())
        return

    if user_id in ADMIN_IDS and admin_states.get(user_id) == "waiting_link":
        admin_states.pop(user_id, None)
        if message.text and CHANNEL_USER_REGEX.match(message.text.strip()):
            SUBSCRIBE_LINK = get_clean_url(message.text)
            BUTTON_TEXT = "اشترك بالقناة"
            BUTTON_STYLE = "primary"
            await message.reply(BotMessages.SET_SUCCESS, reply_markup=ReplyKeyboardRemove())
        else:
            await message.reply(BotMessages.BAD_LINK, reply_markup=ReplyKeyboardRemove())
        return

    if message.text == "تعيين رابط زر الاشتراك" and user_id in ADMIN_IDS:
        admin_states[user_id] = "waiting_link"
        kb_cancel = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="إلغاء")]], resize_keyboard=True)
        await message.reply(BotMessages.ASK_LINK, reply_markup=kb_cancel)
        return

    if message.text == "عرض الزر" and user_id in ADMIN_IDS:
        await message.reply(BotMessages.PREVIEW_MSG, reply_markup=get_sub_keyboard())
        return

    if not message.text:
        if not is_group:
            await handle_random_replies(message)
        return

    urls = YOUTUBE_REGEX.findall(message.text)
    if urls:
        async with counter_lock:
            current_count = user_task_counts.get(user_id, 0)
            for url in urls:
                if current_count >= 7:
                    break
                current_count += 1
                user_task_counts[user_id] = current_count
                await download_queue.put((message, url, user_id))
        return

    if message.text.startswith("يوت"):
        query = message.text[3:].strip()
        if query:
            async with counter_lock:
                current_count = user_task_counts.get(user_id, 0)
                if current_count < 7:
                    user_task_counts[user_id] = current_count + 1
                    await download_queue.put((message, query, user_id))
            return

    if not is_group:
        await handle_random_replies(message)

async def handle_random_replies(message: Message):
    global welcome_state, active_emoji_tasks
    
    if message.text and YOUTUBE_REGEX.search(message.text):
        await live_typing_reply(message, BotMessages.NOT_FOUND, reply_markup=get_sub_keyboard())
        return

    if welcome_state:
        kb_primary = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="المطور", url="tg://user?id=8597653867", style="primary")]
        ])
        await live_typing_reply(message, BotMessages.RESP_1, reply_markup=kb_primary)
        welcome_state = False
    else:
        kb_danger = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]
        ])
        await live_typing_reply(message, BotMessages.RESP_2, reply_markup=kb_danger)
        welcome_state = True

    emoji_msg = await message.reply("🫦")
    task = asyncio.create_task(emoji_cycle_worker(emoji_msg))
    active_emoji_tasks.append(task)

    if len(active_emoji_tasks) > 3:
        oldest_task = active_emoji_tasks.pop(0)
        oldest_task.cancel()

async def main():
    await init_db()
    asyncio.create_task(queue_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
