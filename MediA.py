import asyncio
import os
import re
import time
import random
import string
from collections import defaultdict
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from yt_dlp import YoutubeDL
import STriNGs
import DATAbase

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

DEVELOPER_ID = "8597653867"
SUPPORT_ID = "8467593882"

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

def get_random_emoji_msg() -> str:
    return f"\n\n{random.choice(STriNGs.EMOJIS)}"

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

def get_buttons():
    kb = [
        [types.InlineKeyboardButton(text=STriNGs.BTN_DEV, url=f"tg://user?id={DEVELOPER_ID}", style="primary")],
        [types.InlineKeyboardButton(text=STriNGs.BTN_SUPPORT, url=f"tg://user?id={SUPPORT_ID}", style="destructive")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

async def animate_text(message: types.Message, text: str):
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

        full_current_text = "\n".join(current_display_lines)
        
        try:
            await sent_msg.edit_text(full_current_text)
            await asyncio.sleep(0.3)
        except Exception:
            pass

    try:
        final_text = text + get_random_emoji_msg()
        await sent_msg.edit_text(final_text, reply_markup=get_buttons())
    except Exception:
        pass

def is_url(text: str) -> bool:
    if re.search(r't\.me', text, re.IGNORECASE):
        return False
    regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return bool(re.match(regex, text))

async def process_download_task(message: types.Message, url_text: str):
    user_id = message.from_user.id
    
    cached_ids = await DATAbase.get_cached_file_ids(url_text)
    if cached_ids:
        try:
            chunks = [cached_ids[i:i + 8] for i in range(0, len(cached_ids), 8)]
            for chunk in chunks:
                media_group = []
                for idx, fid in enumerate(chunk):
                    if idx == 0:
                        caption_text = get_random_emoji_msg().strip()
                        media_group.append(types.InputMediaDocument(media=fid, caption=caption_text))
                    else:
                        media_group.append(types.InputMediaDocument(media=fid))
                
                if len(media_group) == 1:
                    await message.answer_document(media_group[0].media, caption=media_group[0].caption)
                else:
                    await message.answer_media_group(media=media_group)
                    
            await message.answer(STriNGs.SUCCESS_MESSAGE + get_random_emoji_msg(), reply_markup=get_buttons())
            return
        except Exception:
            pass

    cleanup_stale_files()
    progress_msg = await message.answer(STriNGs.PROGRESS_START)
    last_reported_progress = 0
    downloaded_files = []
    
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
                        progress_msg.edit_text(STriNGs.PROGRESS_TEMPLATE.format(percent=last_reported_progress)),
                        asyncio.get_event_loop()
                    )

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'progress_hooks': [ytdl_hook],
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False
    }
    
    try:
        loop = asyncio.get_event_loop()
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
                'format': 'bestvideo+bestaudio/best',
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
                        caption_text = get_random_emoji_msg().strip()
                        media_group.append(types.InputMediaDocument(media=file_input, caption=caption_text))
                    else:
                        media_group.append(types.InputMediaDocument(media=file_input))
                
                if len(media_group) == 1:
                    sent_doc = await message.answer_document(media_group[0].media, caption=media_group[0].caption)
                    uploaded_file_ids.append(sent_doc.document.file_id)
                else:
                    sent_group = await message.answer_media_group(media=media_group)
                    for sent_msg in sent_group:
                        if sent_msg.document:
                            uploaded_file_ids.append(sent_msg.document.file_id)
            
            if uploaded_file_ids:
                await DATAbase.save_cached_file_ids(url_text, uploaded_file_ids)
                
            await message.answer(STriNGs.SUCCESS_MESSAGE + get_random_emoji_msg(), reply_markup=get_buttons())
        else:
            await message.answer(STriNGs.FILE_NOT_FOUND + get_random_emoji_msg())
            
    except Exception as e:
        try:
            await progress_msg.edit_text(STriNGs.ERROR_MESSAGE + get_random_emoji_msg())
        except Exception:
            pass
    finally:
        for filepath in downloaded_files:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
        
        downloads_dir = 'downloads'
        if os.path.exists(downloads_dir):
            for filename in os.listdir(downloads_dir):
                if filename.startswith(str(user_id)):
                    try:
                        os.remove(os.path.join(downloads_dir, filename))
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
            await message.answer(STriNGs.QUEUE_FULL_MESSAGE + get_random_emoji_msg())
            return
            
        await queue.put((message, text))
        
        if user_id not in user_workers or user_workers[user_id].done():
            user_workers[user_id] = asyncio.create_task(user_queue_worker(user_id))
    else:
        current_index = await DATAbase.get_user_step(user_id)
        response_text = STriNGs.RESPONSES[current_index]
        
        next_index = (current_index + 1) % len(STriNGs.RESPONSES)
        await DATAbase.update_user_step(user_id, next_index)
        
        await animate_text(message, response_text)

async def on_startup():
    for admin_id in [DEVELOPER_ID, SUPPORT_ID]:
        try:
            await bot.send_message(chat_id=admin_id, text=STriNGs.STARTUP_MESSAGE)
        except Exception:
            pass

async def main():
    await DATAbase.init_db()
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
