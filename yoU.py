import os
import re
import asyncio
import tempfile
import mimetypes
import gc
import shutil
import random
from pathlib import Path
import orjson
import redis.asyncio as redis
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaDocument, CallbackQuery
from aiogram.enums import ChatType, ChatMemberStatus
import yt_dlp

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

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
ALBUM_SUCCESS_MESSAGE = "تم تنفيذ طلبك تاج راسي العظيم تدلل\nمنو اطيع من بعدك"

BUTTONS_CONFIG = {
    "developer": {"text": "المطور", "url": "tg://user?id=8859860635", "style": "primary"},
    "salwa": {"text": "سلوى", "url": "tg://user?id=8800673233", "style": "success"},
    "join": {"text": "انضموا", "url": "https://t.me/+9frtf-UePGU4NTk5", "style": "danger"},
    "share": {"text": "المشاركة", "url": "https://t.me/share/url?url=https://t.me/+9frtf-UePGU4NTk5", "style": "primary"}
}

sequence_index = 0

EMOJIS_LIST = ["😁", "😡", "🌭", "😭", "😘", "🍓", "🤣", "🥰"]
TIMES_LIST = [2.4, 4.2, 4.8, 3.6, 3.2, 2.3]

current_emojis_pool = []
current_times_pool = []

def get_next_emoji() -> str:
    global current_emojis_pool
    if not current_emojis_pool:
        current_emojis_pool = EMOJIS_LIST.copy()
        random.shuffle(current_emojis_pool)
    return current_emojis_pool.pop()

def get_next_time() -> float:
    global current_times_pool
    if not current_times_pool:
        current_times_pool = TIMES_LIST.copy()
        random.shuffle(current_times_pool)
    return current_times_pool.pop()

async def apply_delayed_reaction(chat_id: int, message_id: int):
    delay = get_next_time()
    emoji = get_next_emoji()
    await asyncio.sleep(delay)
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[types.ReactionTypeEmoji(emoji=emoji)],
            is_big=False
        )
    except Exception:
        pass

def get_next_keyboard() -> InlineKeyboardMarkup:
    global sequence_index
    flow = ["developer", "salwa", "join", "salwa", "share"]
    current_key = flow[sequence_index]
    btn_info = BUTTONS_CONFIG[current_key]
    sequence_index = (sequence_index + 1) % len(flow)
    
    kwargs = {
        "text": btn_info["text"],
        "url": btn_info["url"]
    }
    if "style" in btn_info:
        kwargs["style"] = btn_info["style"]

    button = InlineKeyboardButton(**kwargs)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])

UPPER_MAP = {'a':'A','t':'T','n':'N','m':'M','g':'G','u':'U','f':'F','j':'J','а':'А','и':'И','б':'Б'}
URL_RX = re.compile(r'https?://[^\s]+')
EXCLUDE_RX = re.compile(r'https?://(www\.)?(youtube\.com|youtu\.be|t\.me|telegram\.me|telegram\.dog)/', re.I)

async def get_next_sticker(chat_id: int) -> str:
    try:
        key_list = f"stickers_list:{chat_id}"
        key_pool = f"stickers_pool:{chat_id}"
        key_last = f"stickers_last:{chat_id}"

        stickers = await redis_client.lrange(key_list, 0, -1)
        if not stickers:
            return None

        if len(stickers) == 1:
            return stickers[0]

        pool_raw = await redis_client.get(key_pool)
        pool = orjson.loads(pool_raw) if pool_raw else []

        if not pool:
            pool = stickers.copy()
            random.shuffle(pool)
            last_sticker = await redis_client.get(key_last)
            if last_sticker and len(pool) > 1 and pool[0] == last_sticker:
                pool[0], pool[-1] = pool[-1], pool[0]

        selected = pool.pop(0)
        await redis_client.set(key_pool, orjson.dumps(pool).decode('utf-8'))
        await redis_client.set(key_last, selected)
        return selected
    except Exception:
        return None

async def send_welcome_sticker_if_exists(chat_id: int, reply_to_id: int):
    try:
        sticker_id = await get_next_sticker(chat_id)
        if sticker_id:
            await bot.send_sticker(
                chat_id=chat_id,
                sticker=sticker_id,
                reply_to_message_id=reply_to_id
            )
    except Exception:
        pass

async def send_startup_notification():
    for admin_id in ADMIN_IDS:
        try:
            msg = await bot.send_message(
                chat_id=admin_id, 
                text=STARTUP_MESSAGE, 
                reply_markup=get_next_keyboard()
            )
            asyncio.create_task(apply_delayed_reaction(msg.chat.id, msg.message_id))
            await send_welcome_sticker_if_exists(admin_id, msg.message_id)
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
    try:
        cached_raw = await redis_client.get(f"cache:{url}")
        if cached_raw:
            try:
                cached_data = orjson.loads(cached_raw)
                if isinstance(cached_data, list):
                    for media_group_ids in cached_data:
                        media_group = [InputMediaDocument(media=item['file_id']) for item in media_group_ids]
                        sent_group = await message.reply_media_group(media=media_group)
                        for m in sent_group:
                            asyncio.create_task(apply_delayed_reaction(m.chat.id, m.message_id))
                            await send_welcome_sticker_if_exists(m.chat.id, m.message_id)
                    last_msg = await message.reply(ALBUM_SUCCESS_MESSAGE, reply_markup=get_next_keyboard())
                    asyncio.create_task(apply_delayed_reaction(last_msg.chat.id, last_msg.message_id))
                    await send_welcome_sticker_if_exists(last_msg.chat.id, last_msg.message_id)
                else:
                    status = await message.reply("يتم تنفيذ طلبك تاج راسي العظيم تدلل\nراح يوصل هسا", reply_markup=get_next_keyboard())
                    asyncio.create_task(apply_delayed_reaction(status.chat.id, status.message_id))
                    await send_welcome_sticker_if_exists(status.chat.id, status.message_id)
                    
                    input_media = InputMediaDocument(media=cached_data['file_id'])
                    sent_doc = await status.edit_media(
                        media=input_media,
                        reply_markup=get_next_keyboard()
                    )
                    asyncio.create_task(apply_delayed_reaction(sent_doc.chat.id, sent_doc.message_id))
                    await send_welcome_sticker_if_exists(sent_doc.chat.id, sent_doc.message_id)
                return
            except Exception:
                await redis_client.delete(f"cache:{url}")

        status = await message.reply("يتم تنفيذ طلبك تاج راسي العظيم تدلل\nراح يوصل هسا", reply_markup=get_next_keyboard())
        asyncio.create_task(apply_delayed_reaction(status.chat.id, status.message_id))
        await send_welcome_sticker_if_exists(status.chat.id, status.message_id)
        
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
            def process_download():
                nonlocal temp_dir_to_clean
                tmp_dir = tempfile.mkdtemp()
                temp_dir_to_clean = tmp_dir
                p = Path(tmp_dir)
                
                opts = {
                    'format': 'bestvideo+bestaudio/best',
                    'quiet': True,
                    'outtmpl': str(p / '%(autonumber)03d_%(id)s.%(ext)s'), 
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
                    downloaded_entries = list(info['entries']) if 'entries' in info else [info]
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
                        clean_uploader = re.sub(r'\s+', ' ', clean_uploader).strip() or "Uploader"
                        
                        clean_title = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF\u0400-\u04FF\s]', '', mapped_title)
                        clean_title = re.sub(r'\s+', ' ', clean_title).strip() or "Media"
                        
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
                fs_file = types.FSInputFile(path=res['path'], filename=res['name'])
                input_media = InputMediaDocument(media=fs_file)

                sent_doc = await status.edit_media(
                    media=input_media,
                    reply_markup=get_next_keyboard()
                )
                asyncio.create_task(apply_delayed_reaction(sent_doc.chat.id, sent_doc.message_id))
                await send_welcome_sticker_if_exists(sent_doc.chat.id, sent_doc.message_id)
                
                file_id = sent_doc.document.file_id
                cache_payload = orjson.dumps({'file_id': file_id, 'filename': res['name']}).decode('utf-8')
                await redis_client.set(f"cache:{url}", cache_payload)
            else:
                await status.delete()
                chunks = [media_results[i:i + 8] for i in range(0, len(media_results), 8)]
                for chunk in chunks:
                    media_group = [InputMediaDocument(media=types.FSInputFile(path=item['path'], filename=item['name'])) for item in chunk]
                    
                    if media_group:
                        sent_group = await message.reply_media_group(media=media_group)
                        for m in sent_group:
                            asyncio.create_task(apply_delayed_reaction(m.chat.id, m.message_id))
                            await send_welcome_sticker_if_exists(m.chat.id, m.message_id)
                        
                        group_info = [{'file_id': m.document.file_id} for m in sent_group if m.document]
                        album_cache_data.append(group_info)
                
                last_msg = await message.reply(ALBUM_SUCCESS_MESSAGE, reply_markup=get_next_keyboard())
                asyncio.create_task(apply_delayed_reaction(last_msg.chat.id, last_msg.message_id))
                await send_welcome_sticker_if_exists(last_msg.chat.id, last_msg.message_id)
                if album_cache_data:
                    await redis_client.set(f"cache:{url}", orjson.dumps(album_cache_data).decode('utf-8'))

        except Exception:
            try:
                err_msg = await status.edit_text(ERROR_MESSAGE, reply_markup=get_next_keyboard())
                asyncio.create_task(apply_delayed_reaction(err_msg.chat.id, err_msg.message_id))
                await send_welcome_sticker_if_exists(err_msg.chat.id, err_msg.message_id)
            except Exception:
                pass
        finally:
            reset_all_except_file_id(temp_dir_to_clean)
    except Exception:
        pass

async def process_user_queue(user_id: int):
    lock_key = f"lock:queue_process:{user_id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=10)
    if not acquired:
        return
    try:
        while True:
            active_count = int(await redis_client.get(f"active_tasks:{user_id}") or 0)
            if active_count >= MAX_CONCURRENT_PER_USER:
                break
                
            raw_item = await redis_client.rpop(f"queue:{user_id}")
            if not raw_item:
                break
                
            msg_data, url = orjson.loads(raw_item)
            msg = Message.model_validate(msg_data)
            
            await redis_client.incr(f"active_tasks:{user_id}")
            try:
                await download_and_send(msg, url, user_id)
            finally:
                current_active = await redis_client.decr(f"active_tasks:{user_id}")
                if current_active <= 0:
                    await redis_client.delete(f"active_tasks:{user_id}")
    finally:
        await redis_client.delete(lock_key)

async def enqueue_request(message: Message, url: str):
    user_id = message.from_user.id if message.from_user else message.chat.id
    current_active = int(await redis_client.get(f"active_tasks:{user_id}") or 0)

    if current_active < MAX_CONCURRENT_PER_USER:
        await redis_client.incr(f"active_tasks:{user_id}")
        try:
            await download_and_send(message, url, user_id)
        finally:
            c = await redis_client.decr(f"active_tasks:{user_id}")
            if c <= 0:
                await redis_client.delete(f"active_tasks:{user_id}")
            asyncio.create_task(process_user_queue(user_id))
    else:
        q_size = await redis_client.llen(f"queue:{user_id}")
        if q_size < MAX_QUEUE_PER_USER:
            payload = orjson.dumps([message.model_dump(), url]).decode('utf-8')
            await redis_client.lpush(f"queue:{user_id}", payload)

async def send_user_welcome_msg(message: Message):
    try:
        uid = message.from_user.id if message.from_user else message.chat.id
        idx = int(await redis_client.get(f"tracker:{uid}") or 0)
        
        rep_msg = await message.reply(WELCOME_MSGS[idx], reply_markup=get_next_keyboard())
        asyncio.create_task(apply_delayed_reaction(rep_msg.chat.id, rep_msg.message_id))
        await send_welcome_sticker_if_exists(rep_msg.chat.id, rep_msg.message_id)
        
        next_idx = (idx + 1) % len(WELCOME_MSGS)
        await redis_client.set(f"tracker:{uid}", next_idx)
    except Exception:
        pass

async def can_manage_stickers(chat: types.Chat, user_id: int) -> bool:
    if not user_id:
        return False

    if chat.type == ChatType.PRIVATE:
        return user_id in ADMIN_IDS

    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        try:
            member = await bot.get_chat_member(chat.id, user_id)
            return member.status in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]
        except Exception:
            return False

    if chat.type == ChatType.CHANNEL:
        return True

    return False

@dp.message(F.text == "ستيكر ويلكوم")
async def start_welcome_sticker_mode(message: Message):
    asyncio.create_task(apply_delayed_reaction(message.chat.id, message.message_id))
    user_id = message.from_user.id if message.from_user else 0
    if not await can_manage_stickers(message.chat, user_id):
        return

    chat_id = message.chat.id
    await redis_client.delete(f"stickers_list:{chat_id}")
    await redis_client.delete(f"stickers_pool:{chat_id}")
    await redis_client.delete(f"stickers_last:{chat_id}")
    
    await redis_client.set(f"sticker_mode:{chat_id}", "active")
    
    text = "¹# - ارسل الان الملصق لاضافته مع رسائل\nالبوت"
    sent_msg = await message.reply(text)
    asyncio.create_task(apply_delayed_reaction(sent_msg.chat.id, sent_msg.message_id))
    await redis_client.set(f"last_sticker_msg:{chat_id}", sent_msg.message_id)

@dp.message(F.sticker)
async def handle_incoming_sticker(message: Message):
    chat_id = message.chat.id
    is_mode_active = await redis_client.get(f"sticker_mode:{chat_id}")
    
    if not is_mode_active:
        return

    user_id = message.from_user.id if message.from_user else 0
    if not await can_manage_stickers(message.chat, user_id):
        return

    sticker_file_id = message.sticker.file_id
    await redis_client.rpush(f"stickers_list:{chat_id}", sticker_file_id)

    last_msg_id = await redis_client.get(f"last_sticker_msg:{chat_id}")
    if last_msg_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=int(last_msg_id),
                reply_markup=None
            )
        except Exception:
            pass

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="تم", callback_data="finish_stickers")]]
    )
    
    text = "¹# - الملصق اللذي ارسلته اصبح مضاف مع\nرسائل الويلكوم"
    new_msg = await message.reply(text, reply_markup=keyboard)
    asyncio.create_task(apply_delayed_reaction(new_msg.chat.id, new_msg.message_id))
    await redis_client.set(f"last_sticker_msg:{chat_id}", new_msg.message_id)

@dp.callback_query(F.data == "finish_stickers")
async def finish_stickers_callback(callback: CallbackQuery):
    chat = callback.message.chat
    user_id = callback.from_user.id if callback.from_user else 0
    
    if not await can_manage_stickers(chat, user_id):
        return

    chat_id = chat.id
    await redis_client.delete(f"sticker_mode:{chat_id}")
    await redis_client.delete(f"last_sticker_msg:{chat_id}")

    final_text = "¹# - اكتمال اضافه ملصقات الويلكوم كما ارسلتها\nاوامرك فوك راسي"
    try:
        await callback.message.edit_text(final_text, reply_markup=None)
    except Exception:
        pass
    
    await callback.answer()

@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_group_message(message: Message):
    text = message.text or message.caption or ""
    m = URL_RX.search(text)
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, m.group(0)))
    elif "بوت" in text:
        asyncio.create_task(apply_delayed_reaction(message.chat.id, message.message_id))
        await send_user_welcome_msg(message)

@dp.channel_post()
async def handle_channel_post(message: Message):
    text = message.text or message.caption or ""
    m = URL_RX.search(text)
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, m.group(0)))
    elif "بوت" in text:
        asyncio.create_task(apply_delayed_reaction(message.chat.id, message.message_id))
        await send_user_welcome_msg(message)

@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_private(message: Message):
    asyncio.create_task(apply_delayed_reaction(message.chat.id, message.message_id))
    text = message.text or ""
    m = URL_RX.search(text)
    
    if m and not EXCLUDE_RX.search(m.group(0)):
        asyncio.create_task(enqueue_request(message, m.group(0)))
    else:
        await send_user_welcome_msg(message)

async def main():
    await send_startup_notification()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
