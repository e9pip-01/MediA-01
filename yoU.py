import os
import re
import asyncio
import tempfile
import mimetypes
import gc
import shutil
import urllib.request
from pathlib import Path
import orjson
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from aiogram.enums import ChatType
import yt_dlp

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

ADMIN_IDS = [8859860635, 8800673233]
STARTUP_MESSAGE = "اشتغل البوت مرتلخ مولاي\nارضع عيرك ؟!"

MAX_SIZE_BYTES = 456 * 1024 * 1024
MAX_CONCURRENT_PER_USER = 3
MAX_QUEUE_PER_USER = 3

WELCOME_MSGS = [
    "اهلين وياك بوت ميديا تريد اشتغل \nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

ERROR_MESSAGE = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
TOO_LARGE_MESSAGE = "عيرك طويل هواي دادي وكسي مايكدر\nيشيل هلكد عير"

file_id_cache = {}
user_tasks_count = {}   
user_queues = {}        
user_tracker = {}       

BUTTONS_CONFIG = [
    {"text": "المطور", "url": "tg://user?id=8859860635", "style": "danger"},
    {"text": "سلوى", "url": "tg://user?id=8800673233", "style": "primary"},
    {"text": "انضموا", "url": "https://t.me/+9frtf-UePGU4NTk5", "style": "danger"}
]

current_button_index = 0

def get_next_keyboard() -> InlineKeyboardMarkup:
    global current_button_index
    
    btn_info = BUTTONS_CONFIG[current_button_index]
    
    if btn_info["text"] == "انضموا":
        current_button_index = 1
    elif btn_info["text"] == "سلوى":
        current_button_index = 0
    elif btn_info["text"] == "المطور":
        current_button_index = 2
        
    button = InlineKeyboardButton(
        text=btn_info["text"],
        url=btn_info["url"],
        style=btn_info["style"]
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])

UPPER_MAP = {'a':'A','t':'T','n':'N','m':'M','g':'G','u':'U','f':'F','j':'J','а':'А','и':'И','б':'Б'}
URL_RX = re.compile(r'https?://[^\s]+')
EXCLUDE_RX = re.compile(r'https?://(www\.)?(youtube\.com|youtu\.be|t\.me|telegram\.me|telegram\.dog)/', re.I)

async def send_startup_notification():
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id, 
                text=STARTUP_MESSAGE, 
                reply_markup=get_next_keyboard()
            )
        except Exception:
            pass

def reset_all_except_file_id(temp_dir_path: str = None):
    if temp_dir_path and os.path.exists(temp_dir_path):
        try:
            shutil.rmtree(temp_dir_path, ignore_errors=True)
        except Exception:
            pass
    gc.collect()

async def download_and_send(message: Message, url: str, user_id: int):
    if url in file_id_cache:
        cached_data = file_id_cache[url]
        try:
            if isinstance(cached_data, list):
                for media_group in cached_data:
                    await message.reply_media_group(media=media_group)
            else:
                await message.reply_document(
                    document=cached_data['file_id'], 
                    reply_markup=get_next_keyboard()
                )
            return
        except Exception:
            if url in file_id_cache:
                del file_id_cache[url]

    status = await message.reply("يتم تنفيذ طلبك تاج راسي العظيم تدلل\nراح يوصل هسا", reply_markup=get_next_keyboard())
    loop = asyncio.get_running_loop()
    temp_dir_to_clean = None
    
    last_update_time = loop.time()

    def smart_progress_hook(d):
        nonlocal last_update_time
        if d.get('status') == 'downloading':
            current_time = loop.time()
            if current_time - last_update_time >= 5.0:
                last_update_time = current_time
                msg_text = "يتم تنفيذ طلبك تاج راسي العظيم تدلل\nراح يوصل هسا"
                asyncio.run_coroutine_threadsafe(
                    status.edit_text(msg_text, reply_markup=get_next_keyboard()), loop
                )

    try:
        def check_info_first():
            opts = {
                'quiet': True, 
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'extract_flat': 'in_playlist'
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info

        info_meta = await loop.run_in_executor(None, check_info_first)
        
        def process_download():
            nonlocal temp_dir_to_clean
            tmp_dir = tempfile.mkdtemp()
            temp_dir_to_clean = tmp_dir
            p = Path(tmp_dir)
            
            opts = {
                'format': 'bestvideo+bestaudio/best',
                'quiet': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'outtmpl': str(p / '%%(autonumber)03d_%%(id)s.%%(ext)s'), 
                'max_filesize': MAX_SIZE_BYTES,
                'progress_hooks': [smart_progress_hook],
                'embedsubtitles': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['ar'],
                'postprocessor_args': {
                    'merger': ['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'copy', '-map', '0']
                }
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                downloaded_entries = []
                if 'entries' in info:
                    downloaded_entries = list(info['entries'])
                else:
                    downloaded_entries = [info]
                
                downloaded_files = sorted(list(p.glob('*')))
                media_items = []
                
                for idx, entry in enumerate(downloaded_entries):
                    if not entry:
                        continue
                    
                    target_file = None
                    prefix = f"{idx+1:03d}_"
                    for f in downloaded_files:
                        if f.name.startswith(prefix) or entry.get('id') in f.name:
                            target_file = f
                            break
                    
                    if not target_file or not target_file.exists() or target_file.name == "thumb.jpg":
                        continue
                        
                    raw_uploader = entry.get('uploader') or entry.get('uploader_id') or info.get('uploader') or info.get('uploader_id') or 'Uploader'
                    raw_title = entry.get('title') or 'Media'
                    
                    mapped_uploader = "".join(UPPER_MAP.get(c, c) for c in raw_uploader.lower())
                    mapped_title = "".join(UPPER_MAP.get(c, c) for c in raw_title.lower())
                    
                    clean_uploader = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF\u0400-\u04FF\s_]', '', mapped_uploader)
                    clean_uploader = re.sub(r'\s+', ' ', clean_uploader).strip()
                    
                    clean_title = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF\u0400-\u04FF\s]', '', mapped_title)
                    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                    
                    if not clean_uploader:
                        clean_uploader = "Uploader"
                    if not clean_title:
                        clean_title = "Media"
                    
                    mime, _ = mimetypes.guess_type(str(target_file))
                    ext = target_file.suffix.lstrip('.')
                    
                    name = f"{clean_uploader} - {clean_title}" + (f".{ext}" if ext else "")
                    new_p = p / name
                    target_file.rename(new_p)
                    
                    media_items.append({'path': str(new_p), 'name': name, 'mime': mime})
                    
                return media_items

        media_results = await loop.run_in_executor(None, process_download)
        
        if not media_results:
            raise Exception("No files downloaded")
            
        album_cache_data = []
        
        if len(media_results) == 1:
            res = media_results[0]
            sent_doc = await message.reply_document(
                document=types.FSInputFile(path=res['path'], filename=res['name']),
                reply_markup=get_next_keyboard()
            )
            file_id_cache[url] = {
                'file_id': sent_doc.document.file_id,
                'filename': res['name']
            }
        else:
            chunks = [media_results[i:i + 8] for i in range(0, len(media_results), 8)]
            for chunk in chunks:
                media_group = []
                for item in chunk:
                    mime = item['mime'] or ""
                    fs_file = types.FSInputFile(path=item['path'], filename=item['name'])
                    
                    if mime.startswith('image'):
                        media_group.append(InputMediaPhoto(media=fs_file))
                    elif mime.startswith('video'):
                        media_group.append(InputMediaVideo(media=fs_file))
                    else:
                        media_group.append(InputMediaVideo(media=fs_file) if item['name'].endswith(('mp4', 'mkv', 'webm')) else InputMediaPhoto(media=fs_file))
                
                if media_group:
                    sent_group = await message.reply_media_group(media=media_group)
                    group_ids = [m.photo[-1].file_id if m.photo else m.video.file_id for m in sent_group]
                    album_cache_data.append(group_ids)
            
            if album_cache_data:
                file_id_cache[url] = album_cache_data
                
        await status.delete()

    except Exception:
        try:
            await status.edit_text(ERROR_MESSAGE, reply_markup=get_next_keyboard())
        except Exception:
            pass
    finally:
        reset_all_except_file_id(temp_dir_to_clean)

async def process_user_queue(user_id: int):
    while True:
        queue = user_queues.get(user_id)
        if not queue or queue.empty():
            break
            
        if user_tasks_count.get(user_id, 0) < MAX_CONCURRENT_PER_USER:
            user_tasks_count[user_id] = user_tasks_count.get(user_id, 0) + 1
            msg, url = await queue.get()
            try:
                await download_and_send(msg, url, user_id)
            finally:
                user_tasks_count[user_id] = max(0, user_tasks_count.get(user_id, 1) - 1)
                queue.task_done()
        else:
            await asyncio.sleep(1)

async def enqueue_request(message: Message, url: str):
    user_id = message.from_user.id if message.from_user else message.chat.id

    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()

    q = user_queues[user_id]
    current_active = user_tasks_count.get(user_id, 0)

    if current_active < MAX_CONCURRENT_PER_USER:
        user_tasks_count[user_id] = current_active + 1
        try:
            await download_and_send(message, url, user_id)
        finally:
            user_tasks_count[user_id] = max(0, user_tasks_count.get(user_id, 1) - 1)
            asyncio.create_task(process_user_queue(user_id))
    elif q.qsize() < MAX_QUEUE_PER_USER:
        await q.put((message, url))
    else:
        return

@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_group_message(message: Message):
    text = message.text or message.caption or ""
    m = URL_RX.search(text)
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, m.group(0)))

@dp.channel_post()
async def handle_channel_post(message: Message):
    text = message.text or message.caption or ""
    m = URL_RX.search(text)
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, m.group(0)))

@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_private(message: Message):
    text = message.text or ""
    m = URL_RX.search(text)
    
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, m.group(0)))
    else:
        uid = message.from_user.id
        idx = user_tracker.get(uid, 0)
        await message.reply(WELCOME_MSGS[idx], reply_markup=get_next_keyboard())
        user_tracker[uid] = (idx + 1) % len(WELCOME_MSGS)

async def main():
    await send_startup_notification()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
