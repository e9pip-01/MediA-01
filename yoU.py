import os
import re
import glob
import asyncio
from collections import defaultdict
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

ADMIN_IDS = [
    8606430342,
    8255680206,
    8436425159,
    8800673233
]

RAW_STARTUP_NOTIFY = "اشتغل البوت مرتلخ مولاي\nارضع عيرك ؟!"

def format_expandable_bold(text: str) -> str:
    lines = text.strip().split('\n')
    formatted_lines = [f"**>** **{line}**" if line.strip() else "**>**" for line in lines]
    return '\n'.join(formatted_lines)

RAW_START_DOWNLOAD = "دابلش بتنفيذ طلبك مثل ما صممتني مولاي\nتنفيذ طلباتك هو فكرة سورسك"
RAW_FAILURE = "الرابط غير مدعوم او الموقع غير مدعوم\nههع شم كسي امزح"

RAW_ROTATING_RESPONSES = [
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

response_index = 0
index_lock = asyncio.Lock()

async def get_next_response() -> str:
    global response_index
    async with index_lock:
        response = RAW_ROTATING_RESPONSES[response_index]
        response_index = (response_index + 1) % len(RAW_ROTATING_RESPONSES)
        return response

async def animate_text(bot: Bot, chat_id: int, message_id: int, full_raw_text: str):
    words = full_raw_text.replace('\n', ' ').split()
    if not words:
        return
        
    lines = []
    word_index = 0
    toggle_four = True
    
    while word_index < len(words):
        count = 4 if toggle_four else 3
        chunk = words[word_index:word_index + count]
        if not chunk:
            break
            
        lines.append(" ".join(chunk))
        current_text = "\n".join(lines)
        formatted_text = format_expandable_bold(current_text)
        
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=formatted_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except (TelegramBadRequest, TelegramRetryAfter):
            pass
            
        word_index += count
        toggle_four = not toggle_four
        await asyncio.sleep(0.3)

MAX_CONCURRENT_PER_USER = 3
MAX_QUEUE_PER_USER = 3
MAX_TOTAL_USER_TASKS = MAX_CONCURRENT_PER_USER + MAX_QUEUE_PER_USER

user_semaphores = defaultdict(lambda: asyncio.Semaphore(MAX_CONCURRENT_PER_USER))
user_active_counts = defaultdict(int)
user_locks = defaultdict(asyncio.Lock)

def filter_and_case_text(text: str) -> str:
    if not text:
        return ""
    target_uppercase = {'a', 't', 'u', 'f', 'j', 'n', 'm', 'l', 'g', 'а', 'и', 'б'}
    text_lower = text.lower()
    result_chars = [char.upper() if char in target_uppercase else char for char in text_lower]
    processed_text = "".join(result_chars)
    cleaned = re.sub(r'[^\w\s]', '', processed_text, flags=re.UNICODE)
    return cleaned.strip()

def _sync_download(url: str, download_id: str) -> tuple[str, dict]:
    ydl_opts = {
        'format': 'bv*+ba/b',
        'postprocessor_args': ['-c', 'copy'],
        'outtmpl': f'temp_{download_id}_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info

async def download_and_process(url: str, download_id: str) -> str:
    temp_filename, info = await asyncio.to_thread(_sync_download, url, download_id)
    
    uploader = info.get('uploader') or info.get('channel') or "Unknown"
    title = info.get('title') or "Video"
    
    clean_uploader = filter_and_case_text(uploader)
    clean_title = filter_and_case_text(title)
    
    base_name = f"{clean_uploader} - {clean_title}".strip()
    if base_name == "-":
        base_name = "Media_File"
        
    raw_ext = os.path.splitext(temp_filename)[1]
    final_filename = f"{base_name}{raw_ext}"
    
    os.rename(temp_filename, final_filename)
    return final_filename

def cleanup_files(file_path: str = None, download_id: str = None):
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            
        if download_id:
            for pattern in [f"temp_{download_id}_*", f"*{download_id}*"]:
                for temp_file in glob.glob(pattern):
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
    except Exception:
        pass

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

EXCLUDED_DOMAINS = [r'youtube\.com', r'youtu\.be', r't\.me', r'telegram\.me']

def is_excluded_url(text: str) -> bool:
    for domain in EXCLUDED_DOMAINS:
        if re.search(domain, text, re.IGNORECASE):
            return True
    return False

def contains_valid_url(text: str) -> bool:
    return bool(re.search(r'https?://[^\s]+', text))

async def send_animated_response(message: types.Message, raw_text: str):
    words = raw_text.replace('\n', ' ').split()
    first_chunk = " ".join(words[:4]) if words else "..."
    
    initial_msg = await message.answer(
        format_expandable_bold(first_chunk),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_to_message_id=message.message_id
    )
    await animate_text(bot, message.chat.id, initial_msg.message_id, raw_text)

async def notify_admins():
    words = RAW_STARTUP_NOTIFY.replace('\n', ' ').split()
    first_chunk = " ".join(words[:4]) if words else "..."
    
    for admin_id in ADMIN_IDS:
        try:
            msg = await bot.send_message(
                chat_id=admin_id,
                text=format_expandable_bold(first_chunk),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await animate_text(bot, admin_id, msg.message_id, RAW_STARTUP_NOTIFY)
        except Exception:
            pass

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    raw_response = await get_next_response()
    await send_animated_response(message, raw_response)

@dp.message(F.text)
async def message_handler(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    if not contains_valid_url(text) or is_excluded_url(text):
        raw_response = await get_next_response()
        await send_animated_response(message, raw_response)
        return

    async with user_locks[user_id]:
        if user_active_counts[user_id] >= MAX_TOTAL_USER_TASKS:
            return
        user_active_counts[user_id] += 1

    download_id = f"{user_id}_{message.message_id}"
    file_path = None
    status_msg = None

    try:
        async with user_semaphores[user_id]:
            words = RAW_START_DOWNLOAD.replace('\n', ' ').split()
            first_chunk = " ".join(words[:4]) if words else "..."
            
            status_msg = await message.answer(
                format_expandable_bold(first_chunk),
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_to_message_id=message.message_id
            )
            
            anim_task = asyncio.create_task(
                animate_text(bot, message.chat.id, status_msg.message_id, RAW_START_DOWNLOAD)
            )
            
            file_path = await download_and_process(text, download_id)
            await anim_task
            
            await bot.edit_message_media(
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                media=types.InputMediaDocument(
                    media=types.FSInputFile(file_path),
                    caption=""
                )
            )
    except Exception:
        if status_msg:
            await animate_text(bot, message.chat.id, status_msg.message_id, RAW_FAILURE)
        else:
            await send_animated_response(message, RAW_FAILURE)
    finally:
        cleanup_files(file_path, download_id)
        
        async with user_locks[user_id]:
            user_active_counts[user_id] -= 1

async def main():
    asyncio.create_task(notify_admins())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
