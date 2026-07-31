import os, re, asyncio, tempfile, mimetypes, gc, shutil
from pathlib import Path
import orjson
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message
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

UPPER_MAP = {'a':'A','t':'T','n':'N','m':'M','g':'G','u':'U','f':'F','j':'J','а':'А','и':'И','б':'Б'}
URL_RX = re.compile(r'https?://[^\s]+')
EXCLUDE_RX = re.compile(r'https?://(www\.)?(youtube\.com|youtu\.be|t\.me|telegram\.me|telegram\.dog)/', re.I)

async def send_startup_notification():
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=STARTUP_MESSAGE)
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
            await message.reply_document(
                document=cached_data['file_id'], 
                caption=f"{cached_data['filename']}"
            )
            return
        except Exception:
            del file_id_cache[url]

    status = await message.reply("يتم تنفيذ طلبك تاج راسي العظيم تدلل\nراح يوصل هسا 0%")
    loop = asyncio.get_running_loop()
    temp_dir_to_clean = None
    
    last_step = 0

    def smart_progress_hook(d):
        nonlocal last_step
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = (downloaded / total) * 100
                current_step = int(percent // 15)
                
                if current_step > last_step and current_step <= 6:
                    last_step = current_step
                    display_percent = min(current_step * 15, 100)
                    msg_text = f"يتم تنفيذ طلبك تاج راسي العظيم تدلل\nراح يوصل هسا {display_percent}%"
                    asyncio.run_coroutine_threadsafe(
                        status.edit_text(msg_text), loop
                    )

    try:
        def check_info_first():
            opts = {'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                filesize = info.get('filesize') or info.get('filesize_approx') or 0
                return filesize, info

        filesize, info_meta = await loop.run_in_executor(None, check_info_first)
        
        if filesize > MAX_SIZE_BYTES:
            await status.edit_text(TOO_LARGE_MESSAGE)
            return

        def process_download():
            nonlocal temp_dir_to_clean
            tmp_dir = tempfile.mkdtemp()
            temp_dir_to_clean = tmp_dir
            p = Path(tmp_dir)
            
            opts = {
                'format': 'best',
                'quiet': True,
                'external_downloader': 'aria2c', 
                'external_downloader_args': ['aria2c:', '-s', '16', '-x', '16', '-k', '1M'],
                'outtmpl': str(p / '%(id)s.%(ext)s'), 
                'max_filesize': MAX_SIZE_BYTES,
                'progress_hooks': [smart_progress_hook]
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                fpath = Path(ydl.prepare_filename(info))
                
                clean = lambda s: re.sub(r'\s+', ' ', re.sub(r'[^a-zA-Z0-9\u0600-\u06FF\u0400-\u04FF\s]', '', "".join(UPPER_MAP.get(c, c) for c in (s or "").lower()))).strip()
                
                mime = info.get('mime_type') or (info.get('requested_downloads', [{}])[0].get('mime_type') if info.get('requested_downloads') else None)
                if not mime and fpath.exists(): 
                    mime, _ = mimetypes.guess_type(str(fpath))
                ext = (mimetypes.guess_extension(mime.split(';')[0].strip().lower()) or "").lstrip('.') if mime else info.get('ext', '')
                
                uploader = clean(info.get('uploader') or info.get('uploader_id')) or 'Uploader'
                title = clean(info.get('title')) or 'Media'
                name = f"[{uploader}] - [{title}]" + (f".{ext}" if ext else "")
                
                new_p = p / name
                if fpath.exists(): 
                    fpath.rename(new_p)
                return new_p.read_bytes(), name

        data, name = await loop.run_in_executor(None, process_download)
        
        sent_doc = await message.reply_document(
            document=types.BufferedInputFile(data, filename=name),
            caption=f"{name}"
        )
        
        file_id_cache[url] = {
            'file_id': sent_doc.document.file_id,
            'filename': name
        }
        await status.delete()

    except Exception:
        try:
            await status.edit_text(ERROR_MESSAGE)
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
            break

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
        asyncio.create_task(enqueue_request(message, text.strip()))

@dp.channel_post()
async def handle_channel_post(message: Message):
    text = message.text or message.caption or ""
    m = URL_RX.search(text)
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, text.strip()))

@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_private(message: Message):
    text = message.text or ""
    m = URL_RX.search(text)
    
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, text.strip()))
    else:
        uid = message.from_user.id
        idx = user_tracker.get(uid, 0)
        await message.reply(WELCOME_MSGS[idx])
        user_tracker[uid] = (idx + 1) % len(WELCOME_MSGS)

async def main():
    await send_startup_notification()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
