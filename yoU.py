import os
import re
import asyncio
import mimetypes
from collections import defaultdict
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.enums import ButtonStyle, ChatType
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

redis_client = Redis.from_url(REDIS_URL)
storage = RedisStorage(redis=redis_client)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

TARGET_UPPER = set("ATFGNMUJLАБИ")

ROTATING_TEXTS = [
    "اهلين وياك بوت ميديا تريد اشتغل \nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

text_index = 0
button_index = 0

USER_SEMAPHORES = defaultdict(lambda: asyncio.Semaphore(3))
USER_WAITING_COUNT = defaultdict(int)
MAX_WAITING_ALLOWED = 3

NOTIFY_IDS = [8859860635, 8800673233]

async def send_startup_notifications():
    text = "اشتغل البوت مرتلخ مولاي\nارضع عيرك ؟!"
    for user_id in NOTIFY_IDS:
        try:
            await bot.send_message(chat_id=user_id, text=text)
        except Exception:
            pass

def transform_casing(text: str) -> str:
    res = []
    for char in text:
        lower_c = char.lower()
        upper_c = char.upper()
        if upper_c in TARGET_UPPER:
            res.append(upper_c)
        else:
            res.append(lower_c)
    return "".join(res)

def clean_uploader(uploader: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF\s_]', '', uploader)
    return transform_casing(cleaned)

def clean_title(title: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF\s\-&]', '', title)
    return transform_casing(cleaned)

def extract_ext_from_mime(mime_str: str) -> str:
    if not mime_str:
        return ""
    clean_mime = mime_str.split(';')[0].strip()
    ext = mimetypes.guess_extension(clean_mime)
    if ext:
        return ext.lstrip('.')
    parts = clean_mime.split('/')
    if len(parts) > 1:
        return parts[1]
    return ""

async def get_next_button_markup() -> InlineKeyboardMarkup:
    global button_index
    state = button_index % 3
    button_index += 1
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    if state == 0:
        btn = InlineKeyboardButton(text="سلوى", url="tg://user?id=8800673233", style=ButtonStyle.PRIMARY)
    elif state == 1:
        btn = InlineKeyboardButton(text="المطور", url="tg://user?id=8859860635", style=ButtonStyle.DANGER)
    else:
        btn = InlineKeyboardButton(text="مشاركة", switch_inline_query=f"https://t.me/{bot_username}", style=ButtonStyle.SUCCESS)
        
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])

async def process_media_download(message: Message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    url = message.text.strip()
    
    cache_key = f"media_cache:{url}"
    cached_file_id = await redis_client.get(cache_key)
    
    if cached_file_id:
        file_id_str = cached_file_id.decode('utf-8')
        try:
            await message.reply_document(
                document=file_id_str,
                reply_to_message_id=message.message_id
            )
            await message.reply("نيكني استاهل تشكني اطيعك مثل\nعديمة الكرامة")
            return
        except Exception:
            pass

    await message.reply("راح انفذ طلبك مولاي ودامص عيرك\nالعظيم بكل الوضعيات الزانية")
    
    ydl_opts_info = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
    except Exception:
        await message.reply("الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي")
        return

    uploader_raw = info.get('uploader') or info.get('uploader_id') or "channel"
    title_raw = info.get('title') or "video"
    
    uploader_clean = clean_uploader(uploader_raw)
    title_clean = clean_title(title_raw)
    
    base_filename = f"{uploader_clean} - {title_clean}"
    
    formats = info.get('formats', [])
    
    best_combined = None
    best_combined_res = -1
    
    best_video = None
    best_video_res = -1
    
    best_audio = None
    best_audio_bitrate = -1
    
    for f in formats:
        vcodec = f.get('vcodec')
        acodec = f.get('acodec')
        height = f.get('height') or 0
        abr = f.get('abr') or 0
        
        has_v = vcodec and vcodec != 'none'
        has_a = acodec and acodec != 'none'
        
        if has_v and has_a:
            if height >= best_combined_res:
                best_combined_res = height
                best_combined = f
        elif has_v and not has_a:
            if height >= best_video_res:
                best_video_res = height
                best_video = f
        elif has_a and not has_v:
            if abr >= best_audio_bitrate:
                best_audio_bitrate = abr
                best_audio = f

    use_separate = False
    if best_video and best_audio:
        if best_video_res > best_combined_res:
            use_separate = True
        elif not best_combined:
            use_separate = True

    download_dir = f"dl_{message.message_id}_{user_id}"
    os.makedirs(download_dir, exist_ok=True)
    
    if use_separate:
        v_format_id = best_video['format_id']
        a_format_id = best_audio['format_id']
        
        target_ext = extract_ext_from_mime(best_video.get('mime_type')) or extract_ext_from_mime(best_audio.get('mime_type'))
        
        ydl_opts = {
            'format': f"{v_format_id}+{a_format_id}",
            'outtmpl': os.path.join(download_dir, f"{base_filename}.%(ext)s"),
            'postprocessor_args': {
                'ffmpeg': ['-c', 'copy']
            },
            'quiet': True,
            'no_warnings': True,
        }
        if target_ext:
            ydl_opts['merge_output_format'] = target_ext
    else:
        chosen_format = best_combined or (formats[-1] if formats else None)
        if not chosen_format:
            await message.reply("الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي")
            return
            
        ext = extract_ext_from_mime(chosen_format.get('mime_type'))
        f_id = chosen_format['format_id']
        
        out_pattern = f"{base_filename}.{ext}" if ext else f"{base_filename}.%(ext)s"
        ydl_opts = {
            'format': f_id,
            'outtmpl': os.path.join(download_dir, out_pattern),
            'quiet': True,
            'no_warnings': True,
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await loop.run_in_executor(None, lambda: ydl.download([url]))
            
        files = os.listdir(download_dir)
        if not files:
            raise Exception("No file downloaded")
            
        downloaded_file_path = os.path.join(download_dir, files[0])
        
        doc = FSInputFile(downloaded_file_path)
        sent_doc_msg = await message.reply_document(
            document=doc,
            reply_to_message_id=message.message_id
        )
        
        if sent_doc_msg.document:
            await redis_client.set(cache_key, sent_doc_msg.document.file_id)
            
        await message.reply("نيكني استاهل تشكني اطيعك مثل\nعديمة الكرامة")
        
    except Exception:
        await message.reply("الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي")
    finally:
        if os.path.exists(download_dir):
            for f in os.listdir(download_dir):
                os.remove(os.path.join(download_dir, f))
            os.rmdir(download_dir)

@dp.message(F.text.regexp(r'https?://[^\s]+'))
async def media_handler(message: Message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    sem = USER_SEMAPHORES[user_id]
    
    if sem.locked():
        if USER_WAITING_COUNT[user_id] >= MAX_WAITING_ALLOWED:
            return
        USER_WAITING_COUNT[user_id] += 1
        
    try:
        async with sem:
            if USER_WAITING_COUNT[user_id] > 0:
                USER_WAITING_COUNT[user_id] -= 1
            await process_media_download(message)
    except Exception:
        pass

@dp.message(F.text)
async def text_handler(message: Message):
    chat_type = message.chat.type
    
    if chat_type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        if "بوت" not in message.text:
            return

    global text_index
    current_text = ROTATING_TEXTS[text_index]
    text_index = (text_index + 1) % len(ROTATING_TEXTS)
    
    markup = await get_next_button_markup()
    
    await message.reply(current_text, reply_markup=markup)

async def main():
    await send_startup_notifications()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
