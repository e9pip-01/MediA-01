import os
import re
import random
import asyncio
import mimetypes
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

LAST_REACTIONS = {}
LAST_REACTION_TIMES = {}
ACTIVE_GROUPS = set()

URL_CACHE = {}

REACTIONS_LIST = ["😭", "😘", "🤣", "🥰", "🤗"]
REACTION_TIMES = [2.4, 4.2, 3.2, 2.3, 3.6]

EMOJI_FOODS = ["🥪", "🍣", "🍔", "🥞", "🌭"]
current_food_index = 0
LAST_FOOD_MESSAGES = {}

ENGLISH_UPPER = set("ATFGJUINML")
RUSSIAN_UPPER = set("АБИ")

user_queues = {}
user_active_downloads = {}

START_DOWNLOAD_TEXT = "راح انفذ طلبك مولاي ودامص عيرك العظيم بكل الوضعيات الزانية"

RANDOM_RESPONSES = [
    "اهلين وياك بوت ميديا تريد اشتغل \nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]
current_response_index = 0
current_dev_button_toggle = True

DEVELOPER_IDS = [8467593882, 8597653867]

def get_unique_reaction(chat_id: int) -> str:
    if chat_id not in LAST_REACTIONS:
        LAST_REACTIONS[chat_id] = []
    available = [r for r in REACTIONS_LIST if r not in LAST_REACTIONS[chat_id]]
    if not available:
        available = REACTIONS_LIST
    chosen = random.choice(available)
    LAST_REACTIONS[chat_id].append(chosen)
    if len(LAST_REACTIONS[chat_id]) > 3:
        LAST_REACTIONS[chat_id].pop(0)
    return chosen

def get_unique_time(chat_id: int) -> float:
    if chat_id not in LAST_REACTION_TIMES:
        LAST_REACTION_TIMES[chat_id] = []
    available = [t for t in REACTION_TIMES if t not in LAST_REACTION_TIMES[chat_id]]
    if not available:
        available = REACTION_TIMES
    chosen = random.choice(available)
    LAST_REACTION_TIMES[chat_id].append(chosen)
    if len(LAST_REACTION_TIMES[chat_id]) > 2:
        LAST_REACTION_TIMES[chat_id].pop(0)
    return chosen

async def set_random_reaction(chat_id: int, message_id: int):
    delay = get_unique_time(chat_id)
    await asyncio.sleep(delay)
    try:
        reaction = get_unique_reaction(chat_id)
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[types.ReactionTypeEmoji(emoji=reaction)]
        )
    except:
        pass

async def send_next_food_emoji(chat_id: int, reply_to_msg_id: int):
    global current_food_index
    
    if chat_id in LAST_FOOD_MESSAGES:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=LAST_FOOD_MESSAGES[chat_id])
        except:
            pass

    emoji = EMOJI_FOODS[current_food_index % len(EMOJI_FOODS)]
    current_food_index += 1
    msg = await bot.send_message(chat_id=chat_id, text=emoji, reply_to_message_id=reply_to_msg_id)
    LAST_FOOD_MESSAGES[chat_id] = msg.message_id
    asyncio.create_task(set_random_reaction(chat_id, msg.message_id))

async def send_bot_message(chat_id: int, text: str, reply_to_id: int = None, send_food: bool = True, reply_markup=None) -> types.Message:
    msg = await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_id, reply_markup=reply_markup)
    asyncio.create_task(set_random_reaction(chat_id, msg.message_id))
    if send_food:
        asyncio.create_task(send_next_food_emoji(chat_id, msg.message_id))
    return msg

async def edit_bot_message(msg: types.Message, text: str, send_food: bool = True):
    try:
        await msg.edit_text(text)
    except:
        pass
    asyncio.create_task(set_random_reaction(msg.chat.id, msg.message_id))
    if send_food:
        asyncio.create_task(send_next_food_emoji(msg.chat.id, msg.message_id))

def format_custom_case(text: str) -> str:
    result = []
    for char in text:
        if char.upper() in ENGLISH_UPPER:
            result.append(char.upper())
        elif char.upper() in RUSSIAN_UPPER:
            result.append(char.upper())
        else:
            result.append(char.lower())
    return "".join(result)

def has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))

def has_english_or_russian(text: str) -> bool:
    return bool(re.search(r"[a-zA-Z\u0400-\u04FF]", text))

async def is_admin_or_owner(message: types.Message) -> bool:
    if message.chat.type == "private":
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except:
        return False

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text == "تفعيل")
async def cmd_enable_group(message: types.Message):
    if await is_admin_or_owner(message):
        ACTIVE_GROUPS.add(message.chat.id)
        asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
        await send_bot_message(
            message.chat.id, 
            "تم تفعيل البوت مولاي\nارسل رابط الان", 
            message.message_id, 
            send_food=False
        )

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text == "تعطيل")
async def cmd_disable_group(message: types.Message):
    if await is_admin_or_owner(message):
        ACTIVE_GROUPS.discard(message.chat.id)
        asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
        await send_bot_message(
            message.chat.id, 
            "تم تعطيل اليوت مولاي\nارسل رابط الان", 
            message.message_id, 
            send_food=False
        )

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type != "private":
        return
    await handle_all_text_messages(message)

async def worker(user_id: int):
    while True:
        if user_id not in user_queues or user_queues[user_id].empty():
            break
        
        if user_active_downloads.get(user_id, 0) >= 2:
            await asyncio.sleep(1)
            continue
            
        url, message, is_group = await user_queues[user_id].get()
        user_active_downloads[user_id] = user_active_downloads.get(user_id, 0) + 1
        
        try:
            await download_logic(url, message, is_group)
        finally:
            user_active_downloads[user_id] = max(0, user_active_downloads.get(user_id, 0) - 1)
            user_queues[user_id].task_done()

@dp.message(F.text.startswith("http"))
async def process_download(message: types.Message):
    url = message.text
    
    if "youtube.com" in url or "youtu.be" in url or "t.me" in url or "telegram.dog" in url:
        await handle_all_text_messages(message)
        return

    is_group = message.chat.type in ["group", "supergroup", "channel"]
    
    if is_group:
        if message.chat.id not in ACTIVE_GROUPS:
            return
        if not await is_admin_or_owner(message):
            return

    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    user_id = message.from_user.id
    
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
        
    if user_queues[user_id].qsize() >= 4:
        return
        
    await user_queues[user_id].put((url, message, is_group))
    
    if user_active_downloads.get(user_id, 0) < 2:
        asyncio.create_task(worker(user_id))

async def download_logic(url: str, message: types.Message, is_group: bool):
    status_msg = await send_bot_message(
        message.chat.id, 
        START_DOWNLOAD_TEXT, 
        message.message_id,
        send_food=not is_group
    )

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
    except Exception:
        await edit_bot_message(status_msg, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", send_food=not is_group)
        return

    os.makedirs("downloads", exist_ok=True)
    
    is_playlist = 'entries' in info
    entries = info.get('entries', []) if is_playlist else [info]
    
    downloaded_files = []
    
    for entry_idx, entry in enumerate(entries):
        if not entry:
            continue
        formats = entry.get('formats', [])
        best_combined = None
        best_video_only = None
        best_audio_only = None
        
        for f in formats:
            acodec = f.get('acodec', 'none')
            vcodec = f.get('vcodec', 'none')
            
            if vcodec != 'none' and acodec != 'none':
                if not best_combined or f.get('tbr', 0) > best_combined.get('tbr', 0):
                    best_combined = f
            elif vcodec != 'none' and acodec == 'none':
                if not best_video_only or f.get('tbr', 0) > best_video_only.get('tbr', 0):
                    best_video_only = f
            elif vcodec == 'none' and acodec != 'none':
                if not best_audio_only or f.get('tbr', 0) > best_audio_only.get('tbr', 0):
                    best_audio_only = f

        selected_formats = []
        if best_combined:
            selected_formats = [best_combined]
        elif best_video_only and best_audio_only:
            combined_bitrate = best_combined.get('tbr', 0) if best_combined else 0
            separate_bitrate = (best_video_only.get('tbr', 0) or 0) + (best_audio_only.get('tbr', 0) or 0)
            if separate_bitrate > combined_bitrate:
                selected_formats = [best_video_only, best_audio_only]
            else:
                selected_formats = [best_combined] if best_combined else [best_video_only, best_audio_only]
        elif best_video_only:
            selected_formats = [best_video_only]
        elif best_audio_only:
            selected_formats = [best_audio_only]
            
        if not selected_formats:
            continue

        uploader = entry.get('uploader') or entry.get('channel') or "Creator"
        title = entry.get('title') or "Video"
        
        uploader_clean = "".join([c for c in uploader if c.isalnum() or c in " _-&"])
        uploader_clean = format_custom_case(uploader_clean)
        
        if has_arabic(title):
            title_clean = "".join([str(random.randint(0, 9)) for _ in range(9)])
        else:
            title_clean = "".join([c for c in title if c.isalnum() or c in " -&"])
            title_clean = format_custom_case(title_clean)
            
        rand_suffix = f"_{random.randint(100, 999)}" if len(entries) > 1 else ""
        base_filename = f"{uploader_clean} - {title_clean}{rand_suffix}"
        
        for idx, fmt in enumerate(selected_formats):
            fmt_id = fmt.get('format_id')
            ext = fmt.get('ext', 'mp4')
            
            temp_dl_opts = {
                'format': fmt_id,
                'outtmpl': f'downloads/{base_filename}_temp_{idx}.%(ext)s',
                'quiet': True,
                'no_warnings': True
            }
            
            try:
                await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(temp_dl_opts).download([entry.get('webpage_url') or url]))
                temp_file_name = f"downloads/{base_filename}_temp_{idx}.{ext}"
                
                if os.path.exists(temp_file_name):
                    mime_type, _ = mimetypes.guess_type(temp_file_name)
                    guessed_ext = mimetypes.guess_extension(mime_type) if mime_type else f".{ext}"
                    if not guessed_ext:
                        guessed_ext = f".{ext}"
                    
                    final_name = f"downloads/{base_filename}_{idx}{guessed_ext}"
                    os.rename(temp_file_name, final_name)
                    downloaded_files.append((final_name, mime_type))
            except Exception:
                pass

    if not downloaded_files:
        try:
            await status_msg.edit_text(START_DOWNLOAD_TEXT)
        except:
            pass
        await edit_bot_message(status_msg, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", send_food=not is_group)
        return

    try:
        try:
            await status_msg.edit_text(START_DOWNLOAD_TEXT)
        except:
            pass
            
        is_single_video = False
        if len(downloaded_files) == 1:
            mime = downloaded_files[0][1]
            if mime and "video" in mime:
                is_single_video = True
                
        gif_keyboard = None
        if is_single_video:
            cache_id = f"g_{random.randint(1000, 9999)}"
            URL_CACHE[cache_id] = url
            gif_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="ستيكر GIF", callback_data=cache_id, style="success")]
            ])

        chunk_size = 8
        for i in range(0, len(downloaded_files), chunk_size):
            chunk = downloaded_files[i:i + chunk_size]
            for file_path, mime in chunk:
                file_input = types.FSInputFile(file_path)
                doc_msg = await message.reply_document(
                    document=file_input, 
                    reply_markup=gif_keyboard if is_single_video else None
                )
                asyncio.create_task(set_random_reaction(message.chat.id, doc_msg.message_id))
                try:
                    os.remove(file_path)
                except:
                    pass
            
        await status_msg.delete()
        
        success_msg = await message.reply("نيكني استاهل تشكني اطيعك مثل عديمة الكرامة")
        asyncio.create_task(set_random_reaction(message.chat.id, success_msg.message_id))
    except Exception:
        await edit_bot_message(status_msg, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", send_food=not is_group)

@dp.callback_query(F.data.startswith("g_"))
async def cb_gif_download(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    message_id = callback.message.message_id
    
    cache_id = callback.data
    decoded_url = URL_CACHE.get(cache_id)
    
    if not decoded_url:
        await callback.answer("عذراً، الرابط قديم أو منتهي الصلاحية.", show_alert=True)
        return

    dev_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=dev_keyboard)
    except:
        pass
        
    await callback.answer()
    
    progress_msg = await bot.send_message(chat_id=chat_id, text=START_DOWNLOAD_TEXT, reply_to_message_id=message_id)
    asyncio.create_task(set_random_reaction(chat_id, progress_msg.message_id))
    
    ydl_opts = {
        'format': 'bestvideo[height<=720]/best',
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(decoded_url, download=False))
    except Exception:
        try:
            await progress_msg.delete()
        except:
            pass
        fail_msg = await bot.send_message(chat_id=chat_id, text="الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", reply_to_message_id=message_id)
        asyncio.create_task(set_random_reaction(chat_id, fail_msg.message_id))
        return

    uploader = info.get('uploader') or info.get('channel') or "Creator"
    title = info.get('title') or "Video"
    
    uploader_clean = "".join([c for c in uploader if c.isalnum() or c in " _-&"])
    uploader_clean = format_custom_case(uploader_clean)
    
    if has_arabic(title):
        title_clean = "".join([str(random.randint(0, 9)) for _ in range(9)])
    else:
        title_clean = "".join([c for c in title if c.isalnum() or c in " -&"])
        title_clean = format_custom_case(title_clean)
        
    base_filename = f"{uploader_clean} - {title_clean}_gif.mp4"
    file_path = f"downloads/{base_filename}"
    
    os.makedirs("downloads", exist_ok=True)
    
    temp_dl_opts = {
        'format': 'bestvideo[height<=720]/best',
        'outtmpl': file_path,
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(temp_dl_opts).download([decoded_url]))
    except Exception:
        try:
            await progress_msg.delete()
        except:
            pass
        fail_msg = await bot.send_message(chat_id=chat_id, text="الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", reply_to_message_id=message_id)
        asyncio.create_task(set_random_reaction(chat_id, fail_msg.message_id))
        return

    try:
        await progress_msg.delete()
    except:
        pass

    if os.path.exists(file_path):
        try:
            file_input = types.FSInputFile(file_path)
            
            success_gif = await bot.send_animation(
                chat_id=chat_id, 
                animation=file_input, 
                reply_to_message_id=message_id, 
                has_spoiler=True
            )
            asyncio.create_task(set_random_reaction(chat_id, success_gif.message_id))
            os.remove(file_path)
            
            success_msg = await bot.send_message(chat_id=chat_id, text="نيكني استاهل تشكني اطيعك مثل عديمة الكرامة", reply_to_message_id=success_gif.message_id)
            asyncio.create_task(set_random_reaction(chat_id, success_msg.message_id))
        except Exception:
            fail_msg = await bot.send_message(chat_id=chat_id, text="الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", reply_to_message_id=message_id)
            asyncio.create_task(set_random_reaction(chat_id, fail_msg.message_id))
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        fail_msg = await bot.send_message(chat_id=chat_id, text="الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", reply_to_message_id=message_id)
        asyncio.create_task(set_random_reaction(chat_id, fail_msg.message_id))

@dp.message(F.text == "بوت")
async def handle_bot_keyword_in_group(message: types.Message):
    is_group = message.chat.type in ["group", "supergroup", "channel"]
    if is_group and message.chat.id in ACTIVE_GROUPS:
        if await is_admin_or_owner(message):
            asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
            await send_next_food_emoji(message.chat.id, message.message_id)

@dp.message(F.text)
async def handle_all_text_messages(message: types.Message):
    is_group = message.chat.type in ["group", "supergroup", "channel"]
    
    if is_group:
        if message.chat.id in ACTIVE_GROUPS:
            if await is_admin_or_owner(message):
                asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
        return

    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))

    if has_english_or_russian(message.text) and not message.text.startswith("http"):
        formatted_text = format_custom_case(message.text)
        await send_bot_message(
            message.chat.id,
            formatted_text,
            reply_to_id=message.message_id,
            send_food=True
        )
        return

    global current_response_index, current_dev_button_toggle
    response_text = RANDOM_RESPONSES[current_response_index % len(RANDOM_RESPONSES)]
    current_response_index += 1

    if current_dev_button_toggle:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="المطور", url="tg://user?id=8467593882", style="danger")]
        ])
    else:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8597653867", style="primary")]
        ])
    
    current_dev_button_toggle = not current_dev_button_toggle

    await send_bot_message(
        message.chat.id,
        response_text,
        reply_to_id=message.message_id,
        send_food=True,
        reply_markup=keyboard
    )

async def main():
    startup_text = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
    dev_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]
    ])
    
    for dev_id in DEVELOPER_IDS:
        try:
            await send_bot_message(
                chat_id=dev_id, 
                text=startup_text, 
                send_food=True, 
                reply_markup=dev_kb
            )
        except:
            pass
            
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
