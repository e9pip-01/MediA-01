import os, re, random, asyncio, yt_dlp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

ACTIVE_GROUPS, URL_CACHE = set(), {}
user_queues, user_active_downloads = {}, {}
current_food_index, current_response_index = 0, 0
current_dev_button_toggle = True

REACTIONS = ["😭", "😘", "🤣", "🥰", "🤗"]
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

async def set_random_reaction(chat_id: int, msg_id: int):
    await asyncio.sleep(random.choice([2.3, 2.4, 3.2, 3.6, 4.2]))
    try:
        await bot.set_message_reaction(chat_id, msg_id, [types.ReactionTypeEmoji(emoji=random.choice(REACTIONS))])
    except: pass

async def send_next_food_emoji(chat_id: int, reply_to_id: int):
    global current_food_index
    emoji = FOODS[current_food_index % len(FOODS)]
    current_food_index += 1
    try:
        msg = await bot.send_message(chat_id, emoji, reply_to_message_id=reply_to_id)
        asyncio.create_task(set_random_reaction(chat_id, msg.message_id))
    except: pass

async def send_bot_message(chat_id: int, text: str, reply_to_id: int = None, send_food: bool = True, reply_markup=None):
    msg = await bot.send_message(chat_id, text, reply_to_message_id=reply_to_id, reply_markup=reply_markup)
    asyncio.create_task(set_random_reaction(chat_id, msg.message_id))
    if send_food: asyncio.create_task(send_next_food_emoji(chat_id, msg.message_id))
    return msg

def format_custom_case(text: str) -> str:
    return "".join(c.upper() if c.upper() in set("ATFGJUINMLАБИ") else c.lower() for c in text)

async def is_admin_or_owner(message: types.Message) -> bool:
    if message.chat.type == "private": return True
    try:
        m = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except: return False

@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"تفعيل", "تعطيل"}))
async def cmd_toggle_group(message: types.Message):
    if await is_admin_or_owner(message):
        if message.text == "تفعيل": ACTIVE_GROUPS.add(message.chat.id)
        else: ACTIVE_GROUPS.discard(message.chat.id)
        await send_bot_message(message.chat.id, f"تم {message.text} البوت مولاي\nارسل رابط الان", message.message_id, False)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type == "private": await handle_all_text_messages(message)

async def worker(user_id: int):
    while user_id in user_queues and not user_queues[user_id].empty():
        if user_active_downloads.get(user_id, 0) >= 2:
            await asyncio.sleep(1)
            continue
        url, msg, is_group = await user_queues[user_id].get()
        user_active_downloads[user_id] = user_active_downloads.get(user_id, 0) + 1
        try: await download_logic(url, msg, is_group)
        finally:
            user_active_downloads[user_id] = max(0, user_active_downloads.get(user_id, 0) - 1)
            user_queues[user_id].task_done()

@dp.message(F.text.startswith("http"))
async def process_download(message: types.Message):
    url = message.text
    if any(x in url for x in ["youtube.com", "youtu.be", "t.me", "telegram.dog"]):
        await handle_all_text_messages(message)
        return
    is_group = message.chat.type in ["group", "supergroup"]
    if is_group and (message.chat.id not in ACTIVE_GROUPS or not await is_admin_or_owner(message)): return

    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    user_id = message.from_user.id
    if user_id not in user_queues: user_queues[user_id] = asyncio.Queue()
    if user_queues[user_id].qsize() < 4:
        await user_queues[user_id].put((url, message, is_group))
        if user_active_downloads.get(user_id, 0) < 2: asyncio.create_task(worker(user_id))

async def download_logic(url: str, message: types.Message, is_group: bool, is_gif: bool = False):
    status_msg = await send_bot_message(message.chat.id, START_TEXT, message.message_id, not is_group)
    os.makedirs("downloads", exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'downloads/%(uploader)s - %(title)s.%(ext)s',
        'quiet': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'postprocessor_args': {
            'merger': ['-c', 'copy']
        }
    }
    
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        
        downloads = info.get('requested_downloads', [])
        if downloads and 'filepath' in downloads[0]:
            filename = downloads[0]['filepath']
        else:
            filename = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(info)

        _, actual_ext = os.path.splitext(filename)
        
        title = format_custom_case("".join(c for c in info.get('title', 'Video') if c.isalnum() or c in " -&") if not bool(re.search(r"[\u0600-\u06FF]", info.get('title', ''))) else "".join(str(random.randint(0,9)) for _ in range(9)))
        uploader = format_custom_case("".join(c for c in info.get('uploader', 'Creator') if c.isalnum() or c in " _-&"))
        
        final_filename = f"downloads/{uploader} - {title}{actual_ext}"
        os.rename(filename, final_filename)
        
        await status_msg.delete()
        file_input = types.FSInputFile(final_filename)
        
        if is_gif:
            sent = await bot.send_animation(message.chat.id, file_input, reply_to_message_id=message.message_id, has_spoiler=True)
        else:
            cache_id = f"g_{random.randint(1000, 9999)}"
            URL_CACHE[cache_id] = url
            kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="ستيكر GIF", callback_data=cache_id, style="success")]])
            sent = await message.reply_document(document=file_input, reply_markup=kb)
            
        asyncio.create_task(set_random_reaction(message.chat.id, sent.message_id))
        os.remove(final_filename)
        
        # تم تعديل الرسالة هنا لتكون رداً مباشراً على رسالة الميديا المرسلة من البوت
        success_text = (
            "تغزل بيه اريد اكزكز واشبع رومانسيه\n"
            "اريد اذوب من الغزل\n"
            "اريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك"
        )
        success = await sent.reply(success_text)
        asyncio.create_task(set_random_reaction(message.chat.id, success.message_id))
    except Exception:
        try: await status_msg.delete()
        except: pass
        fail = await bot.send_message(message.chat.id, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", reply_to_message_id=message.message_id)
        asyncio.create_task(set_random_reaction(message.chat.id, fail.message_id))

@dp.callback_query(F.data.startswith("g_"))
async def cb_gif_download(callback: types.CallbackQuery):
    await callback.answer()
    url = URL_CACHE.get(callback.data)
    if not url: return

    try: await callback.message.edit_reply_markup(reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]]))
    except: pass
    
    await download_logic(url, callback.message, False, is_gif=True)

@dp.message(F.text == "بوت")
async def handle_bot_keyword(message: types.Message):
    if message.chat.type in ["group", "supergroup"] and message.chat.id in ACTIVE_GROUPS and await is_admin_or_owner(message):
        asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
        await send_next_food_emoji(message.chat.id, message.message_id)

@dp.message(F.text)
async def handle_all_text_messages(message: types.Message):
    if message.chat.type in ["group", "supergroup"]:
        if message.chat.id in ACTIVE_GROUPS and await is_admin_or_owner(message):
            asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
        return

    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    if bool(re.search(r"[a-zA-Z\u0400-\u04FF]", message.text)) and not message.text.startswith("http"):
        await send_bot_message(message.chat.id, format_custom_case(message.text), message.message_id, True)
        return

    global current_response_index, current_dev_button_toggle
    resp = RANDOM_RESPONSES[current_response_index % len(RANDOM_RESPONSES)]
    current_response_index += 1
    
    dev_btn = [types.InlineKeyboardButton(text="المطور", url="tg://user?id=8467593882", style="danger")] if current_dev_button_toggle else [types.InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8597653867", style="primary")]
    current_dev_button_toggle = not current_dev_button_toggle
    
    await send_bot_message(message.chat.id, resp, message.message_id, True, types.InlineKeyboardMarkup(inline_keyboard=[dev_btn]))

async def main():
    dev_kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]])
    for dev_id in DEVELOPER_IDS:
        try: 
            await send_bot_message(dev_id, "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!", send_food=True, reply_markup=dev_kb)
        except: pass
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
