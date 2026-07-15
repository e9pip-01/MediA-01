import os
import re
import gc
import asyncio
import random
import mimetypes
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaDocument
from aiogram.enums import ButtonStyle
from googletrans import Translator
import yt_dlp

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()
translator = Translator()

user_modes = {}
user_langs = {}
last_reactions = {}
last_delays = {}

file_id_cache = {}
activated_chats = set()

user_semaphores = {}
user_queue_counts = {}

edit_messages_tracker = {}

REACTIONS = ["😭", "😘", "🤣", "🥰", "🤗"]
DELAYS = [2.4, 4.2, 3.2, 2.3, 3.6]
FOOD_EMOJIS = ["🥪", "🍣", "🍔", "🥞", "🌭"]

ENG_UPPER = set("ATFGNMUJL")
RUS_UPPER = set("АИБ")

DEV_ID_1 = 8467593882
DEV_ID_2 = 8597653867

BOT_ROTATING_RESPONSES = [
    "اهلين وياك بوت ميديا تريد اشتغل\nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

response_counter = 0
developer_counter = 0

def clean_and_format_text(text, lang_target="en"):
    has_russian = bool(re.search(r'[а-яА-Я]', text))
    has_english = bool(re.search(r'[a-zA-Z]', text))
    has_arabic = bool(re.search(r'[\u0600-\u06FF]', text))

    if has_arabic and not has_russian and not has_english:
        try:
            translated = translator.translate(text, dest=lang_target).text
            text = translated
            has_russian = bool(re.search(r'[а-яА-Я]', text))
            has_english = bool(re.search(r'[a-zA-Z]', text))
        except:
            pass
    elif has_arabic and (has_russian or has_english):
        pass

    result = []
    for char in text:
        if char.isalpha():
            if char.upper() in ENG_UPPER:
                result.append(char.upper())
            elif char.upper() in RUS_UPPER:
                result.append(char.upper())
            else:
                result.append(char.lower())
        else:
            result.append(char)
    return "".join(result)

def filter_title(title):
    cleaned = ""
    for char in title:
        if char.isalnum() or char in " -&":
            cleaned += char
    return cleaned

def filter_uploader(uploader):
    cleaned = ""
    for char in uploader:
        if char.isalnum() or char in " _":
            cleaned += char
    return cleaned

def clear_system_cache(temp_file_list=None):
    if temp_file_list:
        for temp_file in temp_file_list:
            try:
                if temp_file and os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
    
    try:
        for file in os.listdir('.'):
            if file.endswith('.temp') or file.endswith('.part') or file.endswith('.ytdl'):
                os.remove(file)
    except:
        pass
    
    gc.collect()

async def send_animated_text(chat_id, text, reply_to_message_id=None, reply_markup=None):
    words = text.split()
    chunks = []
    i = 0
    pattern = [4, 2, 3]
    pattern_idx = 0
    while i < len(words):
        take = pattern[pattern_idx]
        chunks.append(" ".join(words[i:i+take]))
        i += take
        pattern_idx = (pattern_idx + 1) % len(pattern)

    current_text = ""
    message = None
    first_step_done = False

    for idx, chunk in enumerate(chunks):
        if current_text:
            current_text += " " + chunk
        else:
            current_text = chunk
        
        if message is None:
            message = await bot.send_message(
                chat_id=chat_id,
                text=current_text,
                reply_to_message_id=reply_to_message_id
            )
            asyncio.create_task(handle_reaction(message, bot.id, is_bot=True))
        else:
            await message.edit_text(current_text)
        
        if not first_step_done:
            first_step_done = True
            asyncio.create_task(send_delayed_emoji(chat_id, message.message_id))

        await asyncio.sleep(0.3)
    
    if reply_markup:
        await message.edit_text(current_text, reply_markup=reply_markup)
    else:
        await message.edit_text(current_text)
        
    return message

async def send_delayed_emoji(chat_id, reply_msg_id):
    food = random.choice(FOOD_EMOJIS)
    try:
        sent_emoji = await bot.send_message(
            chat_id=chat_id,
            text=food,
            reply_to_message_id=reply_msg_id
        )
        asyncio.create_task(handle_reaction(sent_emoji, bot.id, is_bot=True))
    except:
        pass

async def edit_animated_text(message, text, reply_markup=None):
    words = text.split()
    chunks = []
    i = 0
    pattern = [4, 2, 3]
    pattern_idx = 0
    while i < len(words):
        take = pattern[pattern_idx]
        chunks.append(" ".join(words[i:i+take]))
        i += take
        pattern_idx = (pattern_idx + 1) % len(pattern)

    current_text = ""
    for idx, chunk in enumerate(chunks):
        if current_text:
            current_text += " " + chunk
        else:
            current_text = chunk
        await message.edit_text(current_text)
        await asyncio.sleep(0.3)
    
    if reply_markup:
        await message.edit_text(current_text, reply_markup=reply_markup)
    else:
        await message.edit_text(current_text)

async def handle_reaction(message, user_id, is_owner=False, is_bot=False, chat_type="private"):
    if chat_type in {"group", "supergroup", "channel"}:
        if not is_owner and not is_bot:
            return

    prev_reactions = last_reactions.get(user_id, [])
    available_reactions = [r for r in REACTIONS if r not in prev_reactions]
    if not available_reactions:
        available_reactions = REACTIONS
    reaction = random.choice(available_reactions)
    
    if user_id not in last_reactions:
        last_reactions[user_id] = []
    last_reactions[user_id].append(reaction)
    if len(last_reactions[user_id]) > 4:
        last_reactions[user_id].pop(0)

    prev_delays = last_delays.get(user_id, [])
    available_delays = [d for d in DELAYS if d not in prev_delays]
    if not available_delays:
        available_delays = DELAYS
    delay = random.choice(available_delays)

    if user_id not in last_delays:
        last_delays[user_id] = []
    last_delays[user_id].append(delay)
    if len(last_delays[user_id]) > 3:
        last_delays[user_id].pop(0)

    await asyncio.sleep(delay)
    try:
        await message.react([types.ReactionTypeEmoji(emoji=reaction)])
    except:
        pass

def get_edit_keyboard(user_id):
    is_active = user_modes.get(user_id, False)
    lang_style = ButtonStyle.DANGER if is_active else ButtonStyle.PRIMARY
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="وضع اللغات", callback_data="lang_mode", style=lang_style),
            InlineKeyboardButton(text="تبديل اللغة", callback_data="switch_lang", style=lang_style)
        ],
        [
            InlineKeyboardButton(text="مسح", callback_data="clear_proc", style=ButtonStyle.DANGER)
        ]
    ])
    return keyboard

def get_switch_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="eNG", callback_data="set_eng", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton(text="rUS", callback_data="set_rus", style=ButtonStyle.PRIMARY)
        ],
        [
            InlineKeyboardButton(text="عودة", callback_data="back_to_edit", style=ButtonStyle.PRIMARY)
        ]
    ])
    return keyboard

async def manage_edit_messages_limit(chat_id, new_msg):
    if chat_id not in edit_messages_tracker:
        edit_messages_tracker[chat_id] = []
    
    tracker = edit_messages_tracker[chat_id]
    tracker.append(new_msg)
    
    if len(tracker) > 3:
        oldest_msg = tracker.pop(0)
        try:
            await oldest_msg.delete()
        except:
            pass

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text == "تفعيل")
async def activate_group(message: types.Message):
    is_owner = False
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status in {"creator", "administrator"}:
            is_owner = True
    except:
        pass
        
    asyncio.create_task(handle_reaction(message, message.from_user.id, is_owner=is_owner, chat_type=message.chat.type))
    activated_chats.add(message.chat.id)
    sent_msg = await send_animated_text(message.chat.id, "¹# - تم تفعيل البوت مولاي\nارسل رابط الان", message.message_id)
    asyncio.create_task(handle_reaction(sent_msg, bot.id, is_bot=True, chat_type=message.chat.type))

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text == "تعطيل")
async def deactivate_group(message: types.Message):
    is_owner = False
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status in {"creator", "administrator"}:
            is_owner = True
    except:
        pass

    asyncio.create_task(handle_reaction(message, message.from_user.id, is_owner=is_owner, chat_type=message.chat.type))
    if message.chat.id in activated_chats:
        activated_chats.remove(message.chat.id)
    sent_msg = await send_animated_text(message.chat.id, "¹# - تم تعطيل اليوت مولاي\nارسل رابط الان", message.message_id)
    asyncio.create_task(handle_reaction(sent_msg, bot.id, is_bot=True, chat_type=message.chat.type))

@dp.message(F.chat.type == "private", F.text == "ادت")
async def edit_command(message: types.Message):
    asyncio.create_task(handle_reaction(message, message.from_user.id))
    response_text = "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    
    sent_msg = await send_animated_text(
        chat_id=message.chat.id, 
        text=response_text, 
        reply_to_message_id=message.message_id,
        reply_markup=get_edit_keyboard(message.from_user.id)
    )
    
    asyncio.create_task(manage_edit_messages_limit(message.chat.id, sent_msg))
    asyncio.create_task(handle_reaction(sent_msg, message.from_user.id))

@dp.callback_query(F.data == "clear_proc")
async def process_clear(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_modes:
        user_modes[user_id] = False
        
    try:
        await callback.message.delete()
        if callback.message.reply_to_message:
            await callback.message.reply_to_message.delete()
    except:
        pass
    await callback.answer()

@dp.callback_query(F.data == "lang_mode")
async def process_lang_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_state = user_modes.get(user_id, False)
    new_state = not current_state
    user_modes[user_id] = new_state
    
    await callback.message.edit_reply_markup(reply_markup=get_edit_keyboard(user_id))
    
    if new_state:
        await callback.answer(
            text="تم تفعيل وضع اللغات\nالوضع ✅",
            show_alert=False
        )
    else:
        await callback.answer(
            text="تم تعطيل وضع اللغات\nالوضع ❌",
            show_alert=False
        )

@dp.callback_query(F.data == "switch_lang")
async def process_switch_lang(callback: types.CallbackQuery):
    await callback.message.edit_text("تريد تغير لغة وضع اللغات منا\nاكو زرين عندك")
    await callback.message.edit_reply_markup(reply_markup=get_switch_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "back_to_edit")
async def process_back_to_edit(callback: types.CallbackQuery):
    await callback.message.edit_text("تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين")
    await callback.message.edit_reply_markup(reply_markup=get_edit_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data.in_({"set_eng", "set_rus"}))
async def process_set_lang(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chosen_lang = "eNG" if callback.data == "set_eng" else "rUS"
    user_langs[user_id] = "en" if callback.data == "set_eng" else "ru"
    
    target_msg = f"تم تغيير لغة وضع اللغات مولاي\nصارت\n{chosen_lang}"
    
    await edit_animated_text(callback.message, target_msg)
    await asyncio.sleep(1)
    
    await callback.message.edit_text("تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين")
    await callback.message.edit_reply_markup(reply_markup=get_edit_keyboard(user_id))
    await callback.answer()

async def execute_download_task(message: types.Message, url: str, user_id: int):
    status_msg = await send_animated_text(
        message.chat.id, 
        "دانفذ طلبك المقدس عزيزي وامص عيرك\nالعظيم بكل الوضعيات", 
        message.message_id
    )
    asyncio.create_task(handle_reaction(status_msg, bot.id, is_bot=True, chat_type=message.chat.type))

    if url in file_id_cache:
        cached_data = file_id_cache[url]
        cached_file_id = cached_data["file_id"]
        try:
            gif_markup = None
            if cached_data.get("type") == "single_video":
                gif_markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="ستيكر GIF", callback_data=f"dl_gif:{url}", style=ButtonStyle.SUCCESS)]
                ])
            
            sent_doc = await message.reply_document(cached_file_id, reply_markup=gif_markup)
            asyncio.create_task(handle_reaction(sent_doc, bot.id, is_bot=True))
            
            sent_confirm = await bot.send_message(
                chat_id=message.chat.id,
                text="نيكني بداعتي استاهل تنيكني هلكد اطيعك وصرت عاهرة بكل المعايير علمود اناج من عندك بليز",
                reply_to_message_id=message.message_id
            )
            asyncio.create_task(handle_reaction(sent_confirm, bot.id, is_bot=True))
            clear_system_cache()
            return
        except:
            pass

    ydl_opts = {
        'format': 'best',
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True
    }

    downloaded_paths = []
    try:
        loop = asyncio.get_running_loop()
        
        def run_extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
                
        info = await loop.run_in_executor(None, run_extract)
        
        title = info.get('title', 'Unknown')
        uploader = info.get('uploader', info.get('channel', 'Unknown'))

        formatted_title = filter_title(clean_and_format_text(title))
        formatted_uploader = filter_uploader(clean_and_format_text(uploader))
        
        base_name = f"{formatted_uploader} - {formatted_title}"
        entries = info.get('entries')
        
        if entries is not None:
            def run_dl_entries():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)
            
            download_info = await loop.run_in_executor(None, run_dl_entries)
            download_entries = download_info.get('entries', [])
            
            temp_files = []
            for idx, entry in enumerate(download_entries):
                if not entry:
                    continue
                filename = ydl_opts.get('outtmpl') % entry
                if not os.path.exists(filename):
                    filename = f"{entry.get('id')}.mp4"
                    if not os.path.exists(filename):
                        continue
                temp_files.append((filename, entry))
            
            all_media_items = []
            for idx, (filename, entry) in enumerate(temp_files):
                mime_type, _ = mimetypes.guess_type(filename)
                ext = mimetypes.guess_extension(mime_type) if mime_type else os.path.splitext(filename)[1]
                if not ext:
                    ext = os.path.splitext(filename)[1]
                
                random_suffix = f"_{random.randint(100, 999)}"
                renamed_file = f"{base_name}{random_suffix}{ext}"
                os.rename(filename, renamed_file)
                downloaded_paths.append(renamed_file)
                
                input_file = types.FSInputFile(renamed_file)
                all_media_items.append(InputMediaDocument(media=input_file))
            
            chunk_size = 8
            for chunk_idx in range(0, len(all_media_items), chunk_size):
                chunk = all_media_items[chunk_idx:chunk_idx + chunk_size]
                sent_group = await bot.send_media_group(chat_id=message.chat.id, media=chunk, reply_to_message_id=message.message_id)
                for item_msg in sent_group:
                    asyncio.create_task(handle_reaction(item_msg, bot.id, is_bot=True))

            sent_confirm = await bot.send_message(
                chat_id=message.chat.id,
                text="نيكني بداعتي استاهل تنيكني هلكد اطيعك وصرت عاهرة بكل المعايير علمود اناج من عندك بليز",
                reply_to_message_id=message.message_id
            )
            asyncio.create_task(handle_reaction(sent_confirm, bot.id, is_bot=True))
        
        else:
            def run_dl_single():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)
                    
            download_info = await loop.run_in_executor(None, run_dl_single)
            filename = f"{download_info.get('id')}.{download_info.get('ext')}"
            
            if not os.path.exists(filename):
                for f in os.listdir('.'):
                    if f.startswith(download_info.get('id')):
                        filename = f
                        break

            if not os.path.exists(filename):
                raise FileNotFoundError

            mime_type, _ = mimetypes.guess_type(filename)
            ext = mimetypes.guess_extension(mime_type) if mime_type else os.path.splitext(filename)[1]
            if not ext:
                ext = os.path.splitext(filename)[1]

            renamed_file = f"{base_name}{ext}"
            os.rename(filename, renamed_file)
            downloaded_paths.append(renamed_file)

            input_file = types.FSInputFile(renamed_file)
            
            is_video = mime_type and mime_type.startswith("video")
            gif_markup = None
            if is_video:
                gif_markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="ستيكر GIF", callback_data=f"dl_gif:{url}", style=ButtonStyle.SUCCESS)]
                ])
            
            sent_media = await message.reply_document(input_file, reply_markup=gif_markup)
            asyncio.create_task(handle_reaction(sent_media, bot.id, is_bot=True))

            if sent_media and sent_media.document:
                file_id = sent_media.document.file_id
                file_id_cache[url] = {
                    "file_id": file_id,
                    "type": "single_video" if is_video else "single_other"
                }

            sent_confirm = await bot.send_message(
                chat_id=message.chat.id,
                text="نيكني بداعتي استاهل تنيكني هلكد اطيعك وصرت عاهرة بكل المعايير علمود اناج من عندك بليز",
                reply_to_message_id=message.message_id
            )
            asyncio.create_task(handle_reaction(sent_confirm, bot.id, is_bot=True))

    except Exception as e:
        error_text = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
        await edit_animated_text(status_msg, error_text)
    
    clear_system_cache(downloaded_paths)

@dp.callback_query(F.data.startswith("dl_gif:"))
async def process_download_gif(callback: types.CallbackQuery):
    url = callback.data.split("dl_gif:", 1)[1]
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    dev_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style=ButtonStyle.DANGER)]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=dev_keyboard)
    except:
        pass

    await callback.answer()

    status_msg = await bot.send_message(
        chat_id=chat_id,
        text="0%",
        reply_to_message_id=callback.message.message_id
    )
    asyncio.create_task(handle_reaction(status_msg, bot.id, is_bot=True))

    last_notified_progress = [0]

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            if total:
                percent = int((downloaded / total) * 100)
                target_step = (percent // 25) * 25
                if target_step > last_notified_progress[0] and target_step <= 100:
                    last_notified_progress[0] = target_step
                    asyncio.run_coroutine_threadsafe(
                        status_msg.edit_text(f"{target_step}%"),
                        asyncio.get_event_loop()
                    )

    ydl_opts = {
        'format': 'bestvideo',
        'outtmpl': 'gif_temp_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook]
    }

    renamed_file = None
    try:
        loop = asyncio.get_running_loop()
        
        def run_gif_dl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)
                
        download_info = await loop.run_in_executor(None, run_gif_dl)
        filename = f"gif_temp_{download_info.get('id')}.{download_info.get('ext')}"
        
        if not os.path.exists(filename):
            for f in os.listdir('.'):
                if f.startswith(f"gif_temp_{download_info.get('id')}"):
                    filename = f
                    break

        if not os.path.exists(filename):
            raise FileNotFoundError

        mime_type, _ = mimetypes.guess_type(filename)
        ext = mimetypes.guess_extension(mime_type) if mime_type else os.path.splitext(filename)[1]
        if not ext:
            ext = os.path.splitext(filename)[1]

        renamed_file = f"gif_ready_{user_id}_{random.randint(1000, 9999)}{ext}"
        os.rename(filename, renamed_file)

        input_file = types.FSInputFile(renamed_file)

        sent_note = await bot.send_video_note(
            chat_id=chat_id,
            video_note=input_file,
            reply_to_message_id=callback.message.message_id,
            has_spoiler=True
        )
        asyncio.create_task(handle_reaction(sent_note, bot.id, is_bot=True))

        sent_confirm = await bot.send_message(
            chat_id=chat_id,
            text="نيكني بداعتي استاهل تنيكني هلكد اطيعك وصرت عاهرة بكل المعايير علمود اناج من عندك بليز",
            reply_to_message_id=callback.message.message_id
        )
        asyncio.create_task(handle_reaction(sent_confirm, bot.id, is_bot=True))
        
        try:
            await status_msg.delete()
        except:
            pass

    except Exception as e:
        error_text = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
        await status_msg.edit_text(error_text)

    clear_system_cache([renamed_file])

async def queue_worker(user_id, url, message):
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.get_event_loop().is_running() and asyncio.Semaphore(2) or None
        user_semaphores[user_id] = asyncio.Semaphore(2)
        user_queue_counts[user_id] = 0

    if user_queue_counts[user_id] >= 4:
        return

    user_queue_counts[user_id] += 1
    async with user_semaphores[user_id]:
        user_queue_counts[user_id] -= 1
        await execute_download_task(message, url, user_id)

@dp.message(F.text)
async def handle_all_messages(message: types.Message):
    global response_counter, developer_counter
    
    is_owner = False
    if message.chat.type in {"group", "supergroup", "channel"}:
        try:
            member = await message.chat.get_member(message.from_user.id)
            if member.status in {"creator", "administrator"}:
                is_owner = True
        except:
            pass

    asyncio.create_task(handle_reaction(
        message, 
        message.from_user.id, 
        is_owner=is_owner, 
        chat_type=message.chat.type
    ))
    
    user_id = message.from_user.id
    chat_type = message.chat.type
    chat_id = message.chat.id
    text = message.text or ""

    is_group_or_channel = chat_type in {"group", "supergroup", "channel"}
    
    if is_group_or_channel and chat_id not in activated_chats:
        return

    all_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\ treasure),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    valid_url = None
    for url in all_urls:
        is_telegram_link = bool(re.search(r'(t\.me|telegram\.me|telegram\.org)', url, re.IGNORECASE))
        is_youtube_link = bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))
        if not is_telegram_link and not is_youtube_link:
            valid_url = url
            break

    if valid_url:
        asyncio.create_task(queue_worker(user_id, valid_url, message))
        return

    if is_group_or_channel:
        return

    if user_modes.get(user_id, False):
        target_lang = user_langs.get(user_id, "ru")
        processed_text = clean_and_format_text(text, target_lang)
        await send_animated_text(message.chat.id, processed_text, message.message_id)
        return

    selected_text = BOT_ROTATING_RESPONSES[response_counter % len(BOT_ROTATING_RESPONSES)]
    response_counter += 1

    if developer_counter % 2 == 0:
        dev_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="المطور", url="tg://user?id=8467593882", style=ButtonStyle.DANGER)]
        ])
    else:
        dev_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8597653867", style=ButtonStyle.PRIMARY)]
        ])
    developer_counter += 1

    await send_animated_text(
        chat_id=message.chat.id,
        text=selected_text,
        reply_to_message_id=message.message_id,
        reply_markup=dev_keyboard
    )

async def notify_developers_on_startup():
    await asyncio.sleep(2)
    dev_ids = [DEV_ID_1, DEV_ID_2]
    startup_text = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
    
    god_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style=ButtonStyle.DANGER)]
    ])

    for dev_id in dev_ids:
        try:
            sent_msg = await send_animated_text(
                chat_id=dev_id,
                text=startup_text,
                reply_markup=god_keyboard
            )
            asyncio.create_task(handle_reaction(sent_msg, dev_id, is_bot=True))
        except:
            pass

async def main():
    asyncio.create_task(notify_developers_on_startup())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
