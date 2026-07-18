import os
import re
import random
import asyncio
from contextlib import suppress
import yt_dlp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus, ContentType
from aiogram.utils.media_group import MediaGroupBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

ACTIVE_GROUPS: set[int] = set()
MUTED_CHATS: set[int] = set()
URL_CACHE: dict[str, dict] = {}
user_queues: dict[int, asyncio.Queue] = {}
user_active_downloads: dict[int, int] = {}

current_food_index = 0
current_response_index = 0
current_dev_button_toggle = True

REACTIONS = ["🤣", "😡", "😭", "🍓", "🥰", "🫡", "😘"]
FOODS = ["🥪", "🍣", "🍔", "🥞", "🌭"]
DEVELOPER_IDS = [8467593882, 8597653867]

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
    with suppress(Exception):
        await bot.set_message_reaction(
            chat_id, 
            msg_id, 
            [types.ReactionTypeEmoji(emoji=random.choice(REACTIONS))]
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
    if message.chat.id in MUTED_CHATS:
        with suppress(Exception):
            await message.delete()

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text.in_({"قفل الاشعارات", "فتح الاشعارات"}))
@dp.channel_post(F.text.in_({"قفل الاشعارات", "فتح الاشعارات"}))
async def toggle_service_notifications(message: types.Message) -> None:
    if message.from_user and not await is_admin_or_owner(message.chat.id, message.from_user.id):
        return
    
    if message.text == "قفل الاشعارات":
        MUTED_CHATS.add(message.chat.id)
        await send_bot_message(message.chat.id, "¹# - تم قفل الاشعارات مولاي\nكل الاشعارات", message.message_id, False)
    else:
        MUTED_CHATS.discard(message.chat.id)
        await send_bot_message(message.chat.id, "¹# - تم فتح الاشعارات مولاي\nكل الاشعارات", message.message_id, False)

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text.in_({"تفعيل", "تعطيل"}))
@dp.channel_post(F.text.in_({"تفعيل", "تعطيل"}))
async def cmd_toggle_group(message: types.Message) -> None:
    if message.chat.type == "channel" or (message.from_user and await is_admin_or_owner(message.chat.id, message.from_user.id)):
        if message.text == "تفعيل":
            ACTIVE_GROUPS.add(message.chat.id)
        else:
            ACTIVE_GROUPS.discard(message.chat.id)
        await send_bot_message(message.chat.id, f"تم {message.text} البوت مولاي\nارسل رابط الان", message.message_id, False)

@dp.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    if message.chat.type == "private":
        await handle_all_text_messages(message)

async def worker(user_id: int) -> None:
    queue = user_queues.get(user_id)
    if not queue:
        return
        
    while not queue.empty():
        if user_active_downloads.get(user_id, 0) >= 2:
            await asyncio.sleep(1)
            continue
            
        url, msg, is_group = await queue.get()
        user_active_downloads[user_id] = user_active_downloads.get(user_id, 0) + 1
        try:
            await download_logic(url, msg, is_group)
        finally:
            user_active_downloads[user_id] = max(0, user_active_downloads.get(user_id, 0) - 1)
            queue.task_done()

@dp.message(F.text.startswith("http"))
async def process_download(message: types.Message) -> None:
    url = message.text
    if any(x in url for x in ["youtube.com", "youtu.be", "t.me", "telegram.dog"]):
        await handle_all_text_messages(message)
        return
        
    is_group = message.chat.type in {"group", "supergroup"}
    if is_group and (message.chat.id not in ACTIVE_GROUPS or not await is_admin_or_owner(message.chat.id, message.from_user.id)):
        return

    if url in URL_CACHE:
        asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
        success_text = "تغزل بيه اريد اكزكز واشبع رومانسيه\nاريد اذوب من الغزل\nاريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك"
        cached = URL_CACHE[url]
        
        if cached["type"] == "document":
            sent = await message.reply_document(document=cached["file_id"])
        elif cached["type"] == "media_group":
            media_group = MediaGroupBuilder()
            for fid in cached["files"]:
                media_group.add_document(media=fid)
            sent_group = await bot.send_media_group(chat_id=message.chat.id, media=media_group.build(), reply_to_message_id=message.message_id)
            sent = sent_group[-1]
            
        asyncio.create_task(set_random_reaction(message.chat.id, sent.message_id))
        success = await sent.reply(success_text)
        asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
        return

    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    user_id = message.from_user.id
    
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
        
    if user_queues[user_id].qsize() < 4:
        await user_queues[user_id].put((url, message, is_group))
        if user_active_downloads.get(user_id, 0) < 2:
            asyncio.create_task(worker(user_id))

async def download_logic(url: str, message: types.Message, is_group: bool) -> None:
    status_msg = await send_bot_message(message.chat.id, START_TEXT, message.message_id, not is_group)
    os.makedirs("downloads", exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'downloads/%(uploader)s - %(title)s - %(id)s.%(ext)s',
        'quiet': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': False,
        'postprocessor_args': {'merger': ['-c', 'copy']}
    }
    
    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        
        entries = info.get('entries', [info]) if 'entries' in info else [info]
        downloaded_files = []
        
        for entry in entries:
            if not entry: 
                continue
            downloads = entry.get('requested_downloads', [])
            filename = downloads[0]['filepath'] if downloads and 'filepath' in downloads[0] else yt_dlp.YoutubeDL(ydl_opts).prepare_filename(entry)
            if os.path.exists(filename):
                downloaded_files.append(filename)

        await status_msg.delete()
        if not downloaded_files:
            raise Exception("No files downloaded")

        success_text = "تغزل بيه اريد اكزكز واشبع رومانسيه\nاريد اذوب من الغزل\nاريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك"

        if len(downloaded_files) == 1:
            filepath = downloaded_files[0]
            sent = await message.reply_document(document=types.FSInputFile(filepath))
            URL_CACHE[url] = {"type": "document", "file_id": sent.document.file_id}
            
            asyncio.create_task(set_random_reaction(message.chat.id, sent.message_id))
            success = await sent.reply(success_text)
            asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
            with suppress(Exception):
                os.remove(filepath)
        else:
            chunks = [downloaded_files[i:i + 8] for i in range(0, len(downloaded_files), 8)]
            cached_media_group_files = []
            
            for chunk in chunks:
                media_group = MediaGroupBuilder()
                for filepath in chunk:
                    media_group.add_document(media=types.FSInputFile(filepath))
                
                sent_group = await bot.send_media_group(chat_id=message.chat.id, media=media_group.build(), reply_to_message_id=message.message_id)
                
                for msg_item in sent_group:
                    if msg_item.document:
                        cached_media_group_files.append(msg_item.document.file_id)

                asyncio.create_task(set_random_reaction(message.chat.id, sent_group[0].message_id))
                success = await sent_group[-1].reply(success_text)
                asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
                
                for filepath in chunk:
                    with suppress(Exception):
                        os.remove(filepath)
                        
            if cached_media_group_files:
                URL_CACHE[url] = {"type": "media_group", "files": cached_media_group_files}
                
    except Exception:
        with suppress(Exception):
            await status_msg.delete()
        fail = await bot.send_message(message.chat.id, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", reply_to_message_id=message.message_id)
        asyncio.create_task(set_random_reaction(message.chat.id, fail.message_id))

@dp.message(F.text == "بوت")
@dp.channel_post(F.text == "بوت")
async def handle_bot_keyword(message: types.Message) -> None:
    if message.chat.type in {"group", "supergroup", "channel"}:
        if message.chat.id not in ACTIVE_GROUPS:
            return
        if message.chat.type != "channel" and message.from_user and not await is_admin_or_owner(message.chat.id, message.from_user.id):
            return

    global current_response_index, current_dev_button_toggle
    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    
    resp = RANDOM_RESPONSES[current_response_index % len(RANDOM_RESPONSES)]
    current_response_index += 1
    
    dev_btn = (
        [types.InlineKeyboardButton(text="المطور", url="tg://user?id=8467593882", style="danger")]
        if current_dev_button_toggle else
        [types.InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8597653867", style="primary")]
    )
    current_dev_button_toggle = not current_dev_button_toggle
    
    await send_bot_message(message.chat.id, resp, message.message_id, True, types.InlineKeyboardMarkup(inline_keyboard=[dev_btn]))

@dp.message(F.text)
async def handle_all_text_messages(message: types.Message) -> None:
    if message.chat.type in {"group", "supergroup"}:
        if message.chat.id in ACTIVE_GROUPS and await is_admin_or_owner(message.chat.id, message.from_user.id):
            asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
        return

    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    
    if bool(re.search(r"[a-zA-Z\u0400-\u04FF]", message.text)) and not message.text.startswith("http"):
        await send_bot_message(message.chat.id, format_custom_case(message.text), message.message_id, True)
        return

    global current_response_index, current_dev_button_toggle
    resp = RANDOM_RESPONSES[current_response_index % len(RANDOM_RESPONSES)]
    current_response_index += 1
    
    dev_btn = (
        [types.InlineKeyboardButton(text="المطور", url="tg://user?id=8467593882", style="danger")]
        if current_dev_button_toggle else
        [types.InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8597653867", style="primary")]
    )
    current_dev_button_toggle = not current_dev_button_toggle
    
    await send_bot_message(message.chat.id, resp, message.message_id, True, types.InlineKeyboardMarkup(inline_keyboard=[dev_btn]))

async def main() -> None:
    dev_kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]])
    
    for dev_id in DEVELOPER_IDS:
        with suppress(Exception):
            await send_bot_message(dev_id, "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!", send_food=True, reply_markup=dev_kb)
            
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
