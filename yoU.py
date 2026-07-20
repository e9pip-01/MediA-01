import os
import re
import random
import asyncio
import json
from contextlib import suppress
import yt_dlp
import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus, ContentType
from aiogram.utils.media_group import MediaGroupBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

user_queues: dict[int, asyncio.Queue] = {}
user_active_downloads: dict[int, int] = {}

current_food_index = 0
current_response_index = 0
current_dev_button_toggle = True

REACTIONS = ["🤣", "😡", "😭", "🍓", "🥰", "🫡", "😘"]
FOODS = ["🥪", "🍣", "🍔", "🥞", "🌭"]
DEVELOPER_IDS = [8800673233]

START_TEXT = "راح انفذ طلبك مولاي ودامص عيرك\nالعظيم بكل الوضعيات الزانية"

RANDOM_RESPONSES = [
    "اهلين وياك بوت ميديا تريد اشتغل \nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

SERVICE_MESSAGES = F.content_type.in_({
    ContentType.NEW_CHAT_PHOTO, ContentType.DELETE_CHAT_PHOTO, ContentType.NEW_CHAT_TITLE,
    ContentType.NEW_CHAT_MEMBERS, ContentType.LEFT_CHAT_MEMBER, ContentType.PINNED_MESSAGE,
    ContentType.VIDEO_CHAT_STARTED, ContentType.VIDEO_CHAT_ENDED, ContentType.VIDEO_CHAT_PARTICIPANTS_INVITED,
    ContentType.FORUM_TOPIC_CREATED, ContentType.FORUM_TOPIC_CLOSED, ContentType.FORUM_TOPIC_REOPENED,
    ContentType.MESSAGE_AUTO_DELETE_TIMER_CHANGED
})

async def set_random_reaction(chat_id: int, msg_id: int) -> None:
    await asyncio.sleep(random.uniform(2.3, 4.2))
    
    history_key = f"rec_hist:{chat_id}"
    history = await redis_client.lrange(history_key, 0, -1)
    
    available_reactions = [r for r in REACTIONS if r not in history]
    if not available_reactions:
        available_reactions = REACTIONS
        
    chosen_emoji = random.choice(available_reactions)
    
    await redis_client.rpush(history_key, chosen_emoji)
    await redis_client.ltrim(history_key, -6, -1)
    
    with suppress(Exception):
        await bot.set_message_reaction(
            chat_id, 
            msg_id, 
            [types.ReactionTypeEmoji(emoji=chosen_emoji)]
        )

async def send_next_food_emoji(chat_id: int, reply_to_id: int) -> None:
    global current_food_index
    emoji = FOODS[current_food_index % len(FOODS)]
    current_food_index += 1
    with suppress(Exception):
        msg = await bot.send_message(chat_id, emoji, reply_to_message_id=reply_to_id)
        asyncio.create_task(set_random_reaction(chat_id, msg.message_id))

async def send_bot_message(chat_id: int, text: str, reply_to_id: int = None, send_food: bool = True, reply_markup=None) -> types.Message:
    msg = await bot.send_message(chat_id, text, reply_to_message_id=reply_to_id, reply_markup=reply_markup)
    asyncio.create_task(set_random_reaction(chat_id, msg.message_id))
    if send_food:
        asyncio.create_task(send_next_food_emoji(chat_id, msg.message_id))
    return msg

def format_custom_case(text: str) -> str:
    target_chars = set("ATFGJUINMLАБИ")
    return "".join(c.upper() if c.upper() in target_chars else c.lower() for c in text)

async def is_admin_or_owner(chat_id: int, user_id: int) -> bool:
    with suppress(Exception):
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
    return False

@dp.message(SERVICE_MESSAGES)
@dp.channel_post(SERVICE_MESSAGES)
async def delete_all_service_messages(message: types.Message) -> None:
    is_muted = await redis_client.sismember("muted_chats", str(message.chat.id))
    if is_muted:
        with suppress(Exception):
            await message.delete()

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text.in_({"قفل الاشعارات", "فتح الاشعارات"}))
@dp.channel_post(F.text.in_({"قفل الاشعارات", "فتح الاشعارات"}))
async def toggle_service_notifications(message: types.Message) -> None:
    if message.chat.type != "channel" and message.from_user and not await is_admin_or_owner(message.chat.id, message.from_user.id):
        return
    
    if message.text == "قفل الاشعارات":
        await redis_client.sadd("muted_chats", str(message.chat.id))
        await send_bot_message(message.chat.id, "¹# - تم قفل الاشعارات مولاي\nكل الاشعارات", message.message_id, False)
    else:
        await redis_client.srem("muted_chats", str(message.chat.id))
        await send_bot_message(message.chat.id, "¹# - تم فتح الاشعارات مولاي\nكل الاشعارات", message.message_id, False)

async def worker(user_id: int) -> None:
    queue = user_queues.get(user_id)
    if not queue:
        return
    while not queue.empty():
        if user_active_downloads.get(user_id, 0) >= 2:
            await asyncio.sleep(1)
            continue
        url, msg, mute_audio = await queue.get()
        user_active_downloads[user_id] = user_active_downloads.get(user_id, 0) + 1
        try:
            await download_logic(url, msg, mute_audio)
        finally:
            user_active_downloads[user_id] = max(0, user_active_downloads.get(user_id, 0) - 1)
            queue.task_done()

@dp.message(F.text.startswith("http"), F.chat.type == "private")
async def process_download(message: types.Message) -> None:
    url = message.text
    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    user_id = message.from_user.id
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
    if user_queues[user_id].qsize() < 4:
        await user_queues[user_id].put((url, message, False))
        if user_active_downloads.get(user_id, 0) < 2:
            asyncio.create_task(worker(user_id))

@dp.message(F.text == "ستيكر", F.reply_to_message, F.chat.type == "private")
async def process_sticker_reply(message: types.Message) -> None:
    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    reply = message.reply_to_message
    
    file_id = None
    if reply.document:
        file_id = reply.document.file_id
    elif reply.video:
        file_id = reply.video.file_id
        
    if not file_id:
        return
        
    url = await redis_client.get(f"file_to_url:{file_id}")
    if not url:
        return
        
    user_id = message.from_user.id
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
    if user_queues[user_id].qsize() < 4:
        await user_queues[user_id].put((url, message, True))
        if user_active_downloads.get(user_id, 0) < 2:
            asyncio.create_task(worker(user_id))

async def download_logic(url: str, message: types.Message, mute_audio: bool = False) -> None:
    status_msg = await send_bot_message(message.chat.id, START_TEXT, message.message_id, False)
    success_text = "تغزل بيه اريد اكزكز واشبع رومانسيه\nاريد اذوب من الغزل\nاريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك"
    
    if not mute_audio:
        cache_data = await redis_client.get(f"url_cache:{url}")
        if cache_data:
            cached_files = json.loads(cache_data)
            valid_cache = True
            for filepath in cached_files:
                if not os.path.exists(filepath):
                    valid_cache = False
                    break
            
            if valid_cache:
                try:
                    await status_msg.delete()
                    if len(cached_files) == 1:
                        sent = await message.reply_document(document=types.FSInputFile(cached_files[0]))
                        asyncio.create_task(set_random_reaction(message.chat.id, sent.message_id))
                        success = await sent.reply(success_text)
                        asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
                    else:
                        chunks = [cached_files[i:i + 8] for i in range(0, len(cached_files), 8)]
                        for chunk in chunks:
                            media_group = MediaGroupBuilder()
                            for filepath in chunk: 
                                media_group.add_document(media=types.FSInputFile(filepath))
                            sent_group = await bot.send_media_group(chat_id=message.chat.id, media=media_group.build(), reply_to_message_id=message.message_id)
                            success = await sent_group[-1].reply(success_text)
                            asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
                    return
                except Exception:
                    pass

    os.makedirs("downloads", exist_ok=True)
    
    fmt = 'bestvideo/best' if mute_audio else 'bestvideo+bestaudio/best'
    
    ydl_opts = {
        'format': fmt,
        'outtmpl': 'downloads/%(uploader)s - %(title)s - %(id)s.%(ext)s',
        'quiet': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': False,
    }
    if not mute_audio:
        ydl_opts['postprocessor_args'] = {'merger': ['-c', 'copy']}
        
    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        entries = info.get('entries', [info]) if 'entries' in info else [info]
        downloaded_files = []
        for entry in entries:
            if not entry: continue
            downloads = entry.get('requested_downloads', [])
            filename = downloads[0]['filepath'] if downloads and 'filepath' in downloads[0] else yt_dlp.YoutubeDL(ydl_opts).prepare_filename(entry)
            if os.path.exists(filename):
                downloaded_files.append(filename)
        await status_msg.delete()
        if not downloaded_files: raise Exception("No files")
        
        if not mute_audio:
            await redis_client.set(f"url_cache:{url}", json.dumps(downloaded_files))
        
        if len(downloaded_files) == 1:
            filepath = downloaded_files[0]
            sent = await message.reply_document(document=types.FSInputFile(filepath))
            asyncio.create_task(set_random_reaction(message.chat.id, sent.message_id))
            
            if not mute_audio and sent.document:
                await redis_client.set(f"file_to_url:{sent.document.file_id}", url)
                
            success = await sent.reply(success_text)
            asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
        else:
            chunks = [downloaded_files[i:i + 8] for i in range(0, len(downloaded_files), 8)]
            for chunk in chunks:
                media_group = MediaGroupBuilder()
                for filepath in chunk: media_group.add_document(media=types.FSInputFile(filepath))
                sent_group = await bot.send_media_group(chat_id=message.chat.id, media=media_group.build(), reply_to_message_id=message.message_id)
                
                if not mute_audio:
                    for s_msg in sent_group:
                        if s_msg.document:
                            await redis_client.set(f"file_to_url:{s_msg.document.file_id}", url)
                            
                success = await sent_group[-1].reply(success_text)
                asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
    except Exception:
        with suppress(Exception): await status_msg.delete()
        fail = await bot.send_message(message.chat.id, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", reply_to_message_id=message.message_id)
        asyncio.create_task(set_random_reaction(message.chat.id, fail.message_id))

@dp.message(F.text, F.chat.type == "private")
async def handle_private_text_messages(message: types.Message) -> None:
    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    
    clean_text = message.text.strip()
    
    if not clean_text.startswith("/") and bool(re.match(r"^[a-zA-Z\u0400-\u04FF0-9\s.,!?-]+$", clean_text)):
        await send_bot_message(message.chat.id, format_custom_case(message.text), message.message_id, True)
        return
        
    global current_response_index, current_dev_button_toggle
    resp = RANDOM_RESPONSES[current_response_index % len(RANDOM_RESPONSES)]
    current_response_index += 1
    
    dev_btn = ([types.InlineKeyboardButton(text="المطور", url="tg://user?id=8800673233", style="danger")] if current_dev_button_toggle else [types.InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8800673233", style="primary")])
    current_dev_button_toggle = not current_dev_button_toggle
    
    await send_bot_message(message.chat.id, resp, message.message_id, True, types.InlineKeyboardMarkup(inline_keyboard=[dev_btn]))

async def main() -> None:
    dev_kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8800673233", style="danger")]])
    for dev_id in DEVELOPER_IDS:
        with suppress(Exception):
            await send_bot_message(dev_id, "اشتغل البوت مرتلخ مولاي\nارضع عيرك ؟!", send_food=True, reply_markup=dev_kb)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
