import os
import re
import asyncio
import random
import shutil
import mimetypes
from collections import deque
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from deep_translator import GoogleTranslator
import yt_dlp

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise ValueError("No BOT_TOKEN provided in environment variables.")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

file_cache = {}
user_settings = {}
user_states_data = {}
developer_btn_state = {}
user_edit_messages = {}

recent_reactions = deque(maxlen=4)
recent_delays = deque(maxlen=4)

REACTIONS_LIST = ["😭", "😘", "🤣", "🥰", "🤗"]
DELAYS_LIST = [2.4, 4.2, 3.2, 2.3, 3.6]
EMOJIS_LIST = ["🥪", "🍣", "🍔", "🥞", "🌭", "🐈‍⬛", "🪩", "🌮"]

emoji_counter = 0
sent_emojis_tracker = deque()

enabled_chats = set()

user_queues = {}
user_active_jobs = {}

DEVELOPER_IDS = [8467593882, 8597653867]

class BotStates(StatesGroup):
    waiting_for_lang_mode = State()

def clean_temp_files():
    temp_dir = "temp_downloads"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

def filter_title(text):
    return "".join([c for c in text if c.isalnum() or c in [" ", "-", "&"]])

def filter_channel(text):
    return "".join([c for c in text if c.isalnum() or c in [" ", "_"]])

def translate_text(text, dest_lang="en"):
    try:
        return GoogleTranslator(source="auto", target=dest_lang).translate(text)
    except Exception:
        return text

def apply_casing_rules(text):
    en_rules = {"a": "A", "t": "T", "f": "F", "g": "G", "n": "N", "m": "M", "j": "J", "l": "L"}
    ru_rules = {"а": "А", "и": "И", "б": "Б"}
    
    result = []
    for char in text:
        lower_char = char.lower()
        if lower_char in en_rules:
            result.append(en_rules[lower_char])
        elif lower_char in ru_rules:
            result.append(ru_rules[lower_char])
        else:
            result.append(lower_char)
    return "".join(result)

def filter_only_commas(text):
    cleaned = re.sub(r"[^\w\s,]", "", text)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    return cleaned.strip()

def contains_arabic(text):
    return bool(re.search(r"[\u0600-\u06FF]", text))

def contains_russian(text):
    return bool(re.search(r"[\u0400-\u04FF]", text))

def contains_english(text):
    return bool(re.search(r"[a-zA-Z]", text))

def get_next_emoji():
    global emoji_counter
    emoji = EMOJIS_LIST[emoji_counter % len(EMOJIS_LIST)]
    emoji_counter += 1
    return emoji

async def send_tracked_emoji(chat_id: int, reply_to_id: int = None):
    emoji_char = get_next_emoji()
    try:
        emoji_msg = await bot.send_message(
            chat_id=chat_id,
            text=emoji_char,
            reply_to_message_id=reply_to_id
        )
        asyncio.create_task(handle_random_reaction(emoji_msg.chat.id, emoji_msg.message_id, is_bot_message=True))
        
        sent_emojis_tracker.append((chat_id, emoji_msg.message_id))
        
        while len(sent_emojis_tracker) > 24:
            old_chat_id, old_msg_id = sent_emojis_tracker.popleft()
            try:
                await bot.delete_message(chat_id=old_chat_id, message_id=old_msg_id)
            except Exception:
                pass
    except Exception:
        pass

async def is_chat_creator(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator"]
    except Exception:
        return False

async def track_and_clean_edit_messages(chat_id: int, user_id: int, new_msg_id: int):
    if user_id not in user_edit_messages:
        user_edit_messages[user_id] = []
    
    user_edit_messages[user_id].append(new_msg_id)
    
    while len(user_edit_messages[user_id]) > 3:
        oldest_msg_id = user_edit_messages[user_id].pop(0)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=oldest_msg_id)
        except Exception:
            pass

async def simulate_parallel_typing(message: types.Message, full_text: str):
    lines = full_text.split("\n")
    lines_words = [line.split() for line in lines]
    max_words_count = max(len(w) for w in lines_words) if lines_words else 0
    
    steps = []
    current_limit = 0
    alternate_state = 0
    
    while current_limit < max_words_count:
        if alternate_state == 0:
            current_limit += 4
            alternate_state = 1
        elif alternate_state == 1:
            current_limit += 2
            alternate_state = 2
        else:
            current_limit += 3
            alternate_state = 1
        steps.append(current_limit)
        
    is_first_step = True
    for limit in steps:
        current_lines = []
        for words in lines_words:
            current_words = words[:limit]
            current_lines.append(" ".join(current_words))
            
        display_text = "\n".join(current_lines)
        try:
            await message.edit_text(display_text)
        except Exception:
            pass
            
        if is_first_step:
            is_first_step = False
            asyncio.create_task(send_tracked_emoji(message.chat.id, message.message_id))
            
        await asyncio.sleep(0.35)
        
    try:
        await message.edit_text(full_text)
    except Exception:
        pass
    return full_text

async def handle_random_reaction(chat_id: int, message_id: int, from_user_id: int = None, is_bot_message: bool = False):
    try:
        chat_info = await bot.get_chat(chat_id)
        is_private = chat_info.type == "private"
    except Exception:
        is_private = True

    if not is_private:
        if is_bot_message:
            pass
        elif from_user_id:
            is_creator = await is_chat_creator(chat_id, from_user_id)
            if not is_creator:
                return
        else:
            return

    available_reactions = [r for r in REACTIONS_LIST if r not in recent_reactions]
    if not available_reactions:
        available_reactions = REACTIONS_LIST
    reaction = random.choice(available_reactions)
    recent_reactions.append(reaction)
    
    available_delays = [d for d in DELAYS_LIST if d not in recent_delays]
    if not available_delays:
        available_delays = DELAYS_LIST
    delay = random.choice(available_delays)
    recent_delays.append(delay)
    
    await asyncio.sleep(delay)
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[types.ReactionTypeEmoji(emoji=reaction)],
            is_big=False
        )
    except Exception:
        pass

def get_edit_keyboard(is_active: bool = False):
    style = "danger" if is_active else "primary"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="وضع اللغات", callback_data="lang_mode_toggle", style=style),
            InlineKeyboardButton(text="تبديل اللغة", callback_data="switch_language", style=style)
        ],
        [
            InlineKeyboardButton(text="مسح", callback_data="delete_edit_panel", style="danger")
        ]
    ])
    return keyboard

def get_alternating_developer_keyboard(user_id: int):
    state = developer_btn_state.get(user_id, 0)
    
    if state == 0:
        btn_text = "المطور"
        btn_url = "tg://user?id=8467593882"
        btn_style = "danger"
        developer_btn_state[user_id] = 1
    else:
        btn_text = "تواصل مع المطور"
        btn_url = "tg://user?id=8597653867"
        btn_style = "primary"
        developer_btn_state[user_id] = 0
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=btn_text, 
                url=btn_url,
                style=btn_style
            )
        ]
    ])
    return keyboard

async def send_startup_notification(dev_id: int):
    try:
        start_message = await bot.send_message(chat_id=dev_id, text="بدء")
        asyncio.create_task(handle_random_reaction(start_message.chat.id, start_message.message_id, is_bot_message=True))
        
        target_text = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
        await simulate_parallel_typing(start_message, target_text)
        
        kb = get_alternating_developer_keyboard(dev_id)
        await start_message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text == "تفعيل")
async def enable_bot_handler(message: types.Message):
    asyncio.create_task(handle_random_reaction(message.chat.id, message.message_id, from_user_id=message.from_user.id))
    if await is_chat_creator(message.chat.id, message.from_user.id):
        enabled_chats.add(message.chat.id)
        sent_msg = await message.reply("تفعيل")
        asyncio.create_task(handle_random_reaction(sent_msg.chat.id, sent_msg.message_id, is_bot_message=True))
        target_text = "¹# - تم تفعيل اليوت مولاي\nاليوتيوب شغال"
        await simulate_parallel_typing(sent_msg, target_text)

@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}), F.text == "تعطيل")
async def disable_bot_handler(message: types.Message):
    asyncio.create_task(handle_random_reaction(message.chat.id, message.message_id, from_user_id=message.from_user.id))
    if await is_chat_creator(message.chat.id, message.from_user.id):
        if message.chat.id in enabled_chats:
            enabled_chats.remove(message.chat.id)
        sent_msg = await message.reply("تعطيل")
        asyncio.create_task(handle_random_reaction(sent_msg.chat.id, sent_msg.message_id, is_bot_message=True))
        target_text = "¹# - تم تعطيل اليوت مولاي\nاليوتيوب معطل"
        await simulate_parallel_typing(sent_msg, target_text)

@dp.message(F.chat.type == "private", F.text == "ادت")
async def edit_command_handler(message: types.Message, state: FSMContext):
    asyncio.create_task(handle_random_reaction(message.chat.id, message.message_id, from_user_id=message.from_user.id))
    
    sent_msg = await message.reply("ادت")
    asyncio.create_task(handle_random_reaction(sent_msg.chat.id, sent_msg.message_id, is_bot_message=True))
    
    target_text = "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    await simulate_parallel_typing(sent_msg, target_text)
    
    current_state = await state.get_state()
    is_active = (current_state == BotStates.waiting_for_lang_mode.state)
    
    await sent_msg.edit_reply_markup(reply_markup=get_edit_keyboard(is_active=is_active))
    await track_and_clean_edit_messages(message.chat.id, message.from_user.id, sent_msg.message_id)

@dp.callback_query(F.data == "delete_edit_panel")
async def delete_edit_panel_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback_query.from_user.id
    
    if user_id in user_edit_messages:
        if callback_query.message.message_id in user_edit_messages[user_id]:
            user_edit_messages[user_id].remove(callback_query.message.message_id)
            
    try:
        await callback_query.message.delete()
    except Exception:
        pass
        
    if callback_query.message.reply_to_message:
        try:
            await callback_query.message.reply_to_message.delete()
        except Exception:
            pass
            
    await callback_query.answer()

@dp.callback_query(F.data == "lang_mode_toggle")
async def lang_mode_toggle_handler(callback_query: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state == BotStates.waiting_for_lang_mode.state:
        await state.clear()
        try:
            await callback_query.message.edit_reply_markup(reply_markup=get_edit_keyboard(is_active=False))
        except Exception:
            pass
        await callback_query.answer(text="تم تعطيل وضع اللغات\nالوضع ❌", show_alert=True)
    else:
        await state.set_state(BotStates.waiting_for_lang_mode)
        try:
            await callback_query.message.edit_reply_markup(reply_markup=get_edit_keyboard(is_active=True))
        except Exception:
            pass
        await callback_query.answer(text="تم تفعيل وضع اللغات\nالوضع ✅", show_alert=True)

@dp.callback_query(F.data == "switch_language")
async def switch_language_handler(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="انكليزية  🇺🇸", callback_data="set_lang_en", style="success"),
            InlineKeyboardButton(text="روسية  🇷🇺", callback_data="set_lang_ru", style="success")
        ]
    ])
    try:
        await callback_query.message.edit_text("تغيير اللغة", reply_markup=keyboard)
    except Exception:
        pass
    await callback_query.answer()

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_lang_callback(callback_query: types.CallbackQuery, state: FSMContext):
    name_map = {"en": "الانكليزية", "ru": "الروسية"}
    lang_code = callback_query.data.split("_")[-1]
    user_id = callback_query.from_user.id
    
    lang_name = name_map.get(lang_code, "الانكليزية")
    user_settings[user_id] = lang_code
    
    try:
        await callback_query.message.delete()
    except Exception:
        pass
        
    reply_msg = await bot.send_message(
        chat_id=callback_query.message.chat.id, 
        text="تغيير لغة وضع اللغات",
        reply_to_message_id=callback_query.message.reply_to_message.message_id if callback_query.message.reply_to_message else None
    )
    asyncio.create_task(handle_random_reaction(reply_msg.chat.id, reply_msg.message_id, is_bot_message=True))
    
    target_text = f"تم تبديل لغة وضع اللغات الى\n{lang_name}"
    await simulate_parallel_typing(reply_msg, target_text)
    
    current_state = await state.get_state()
    is_active = (current_state == BotStates.waiting_for_lang_mode.state)
    await reply_msg.edit_reply_markup(reply_markup=get_edit_keyboard(is_active=is_active))
    
    await track_and_clean_edit_messages(callback_query.message.chat.id, user_id, reply_msg.message_id)
    await callback_query.answer()

@dp.message(BotStates.waiting_for_lang_mode, F.chat.type == "private")
async def lang_mode_processing(message: types.Message):
    asyncio.create_task(handle_random_reaction(message.chat.id, message.message_id, from_user_id=message.from_user.id))
    text = message.text
    user_id = message.from_user.id
    target_lang = user_settings.get(user_id, "en")
    
    is_ar = contains_arabic(text)
    is_ru = contains_russian(text)
    is_en = contains_english(text)
    
    has_formatted_lang = is_en or is_ru
    
    words = text.split()
    has_other_lang = False
    for w in words:
        if not contains_arabic(w) and not contains_english(w) and not contains_russian(w):
            if any(c.isalpha() for c in w):
                has_other_lang = True
                break

    result_text = ""
    
    if is_ar and not has_formatted_lang and not has_other_lang:
        translated = translate_text(text, dest_lang=target_lang)
        if target_lang == "en":
            translated = filter_only_commas(translated)
        result_text = apply_casing_rules(translated)
    elif is_ar and has_formatted_lang:
        result_text = apply_casing_rules(text)
    elif is_ar and not has_formatted_lang and has_other_lang:
        processed_words = []
        for w in words:
            if contains_arabic(w):
                processed_words.append(w)
            elif any(c.isalpha() for c in w):
                translated_word = translate_text(w, dest_lang=target_lang)
                if target_lang == "en":
                    translated_word = filter_only_commas(translated_word)
                processed_words.append(translated_word)
            else:
                processed_words.append(w)
        combined_text = " ".join(processed_words)
        result_text = apply_casing_rules(combined_text)
    else:
        translated = translate_text(text, dest_lang=target_lang)
        if target_lang == "en":
            translated = filter_only_commas(translated)
        result_text = apply_casing_rules(translated)
        
    random_emoji = get_next_emoji()
    reply_msg = await message.reply(random_emoji)
    asyncio.create_task(handle_random_reaction(reply_msg.chat.id, reply_msg.message_id, is_bot_message=True))
    await simulate_parallel_typing(reply_msg, result_text)

class ProgressTracker:
    def __init__(self, bot, message, query):
        self.bot = bot
        self.message = message
        self.query = query
        self.last_reported_step = 0

    def progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                percentage = int((downloaded / total) * 100)
                next_step = (percentage // 25) * 25
                if next_step > self.last_reported_step and next_step <= 100:
                    self.last_reported_step = next_step
                    asyncio.run_coroutine_threadsafe(
                        update_percentage(self.message, next_step),
                        asyncio.get_event_loop()
                    )

async def process_youtube_job(message: types.Message, query: str):
    info_msg_text = f"بدءت بالعثور ع\n{query}\nاه انتظر دادي بليز"
    
    status_msg = await message.reply("بدء")
    asyncio.create_task(handle_random_reaction(status_msg.chat.id, status_msg.message_id, is_bot_message=True))
    await simulate_parallel_typing(status_msg, info_msg_text)
    
    percent_msg = await status_msg.reply("0%")
    asyncio.create_task(handle_random_reaction(percent_msg.chat.id, percent_msg.message_id, is_bot_message=True))
    
    if query in file_cache:
        for percent in range(25, 101, 25):
            await update_percentage(percent_msg, percent)
            await asyncio.sleep(0.1)
        
        cached_file_path = file_cache[query]
        if os.path.exists(cached_file_path):
            try:
                mime_type, _ = mimetypes.guess_type(cached_file_path)
                if not mime_type:
                    mime_type = "audio/mpeg"
                
                filename = os.path.basename(cached_file_path)
                with open(cached_file_path, "rb") as audio_file:
                    input_file = BufferedInputFile(audio_file.read(), filename=filename)
                
                await bot.send_audio(
                    chat_id=message.chat.id,
                    audio=input_file,
                    reply_to_message_id=message.message_id
                )
                
                try:
                    await percent_msg.delete()
                except Exception:
                    pass
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                return
            except Exception:
                pass

    clean_temp_files()
    temp_dir = "temp_downloads"
    tracker = ProgressTracker(bot, percent_msg, query)
    
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "progress_hooks": [tracker.progress_hook],
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = await loop.run_in_executor(
                None, lambda: ydl.extract_info(f"ytsearch1:{query}", download=True)
            )
            
            if not info_dict or "entries" not in info_dict or not info_dict["entries"]:
                raise Exception("No results found")
                
            video_info = info_dict["entries"][0]
            title = video_info.get("title", "Audio")
            uploader = video_info.get("uploader", "")
            
            downloaded_file_path = None
            for file_name in os.listdir(temp_dir):
                full_path = os.path.join(temp_dir, file_name)
                if os.path.isfile(full_path) and file_name.startswith(video_info["id"]):
                    downloaded_file_path = full_path
                    break
            
            if not downloaded_file_path or not os.path.exists(downloaded_file_path):
                raise Exception("Downloaded file not found")
            
            mime_type, _ = mimetypes.guess_type(downloaded_file_path)
            if not mime_type:
                mime_type = "audio/mpeg"
                
            detected_ext = mimetypes.guess_extension(mime_type) or ".mp3"
            if detected_ext.startswith("."):
                detected_ext = detected_ext[1:]

            if tracker.last_reported_step < 75:
                await update_percentage(percent_msg, 75)
            
            if contains_arabic(title):
                title = translate_text(title, "en")
            if contains_arabic(uploader):
                uploader = translate_text(uploader, "en")
                
            processed_title = apply_casing_rules(filter_title(title))
            processed_uploader = apply_casing_rules(filter_channel(uploader)) if uploader else ""
            
            if processed_uploader:
                final_filename = f"{processed_uploader} - {processed_title}.{detected_ext}"
            else:
                final_filename = f"{processed_title}.{detected_ext}"
                
            await update_percentage(percent_msg, 100)
            
            success_text = "اكتمل اليوت وتم ارفق اغنيتك بالشات\nماعليك سوى الاستماع لها"
            await status_msg.edit_text("اكتمل")
            await simulate_parallel_typing(status_msg, success_text)
            
            final_saved_path = os.path.join(temp_dir, final_filename)
            os.rename(downloaded_file_path, final_saved_path)
            
            with open(final_saved_path, "rb") as audio_file:
                input_file = BufferedInputFile(audio_file.read(), filename=final_filename)
                
            await bot.send_audio(
                chat_id=message.chat.id,
                audio=input_file,
                reply_to_message_id=message.message_id
            )
            
            file_cache[query] = final_saved_path
            
            try:
                await percent_msg.delete()
            except Exception:
                pass
            try:
                await status_msg.delete()
            except Exception:
                pass
                
    except Exception:
        fail_text = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
        try:
            await status_msg.edit_text("فشل")
            await simulate_parallel_typing(status_msg, fail_text)
            await percent_msg.delete()
        except Exception:
            pass

async def manage_user_queue(user_id: int):
    while True:
        queue = user_queues.get(user_id)
        if not queue:
            break
            
        active_count = user_active_jobs.get(user_id, 0)
        if active_count >= 2:
            await asyncio.sleep(0.5)
            continue
            
        if not queue:
            break
            
        try:
            message, query = queue.popleft()
        except IndexError:
            break
            
        user_active_jobs[user_id] = active_count + 1
        
        try:
            await process_youtube_job(message, query)
        except Exception:
            pass
        finally:
            user_active_jobs[user_id] = max(0, user_active_jobs.get(user_id, 1) - 1)
            
        if not queue and user_active_jobs.get(user_id, 0) == 0:
            user_queues.pop(user_id, None)
            user_active_jobs.pop(user_id, None)
            break

@dp.message(F.text.startswith("يوت"))
async def youtube_download_dispatcher(message: types.Message):
    is_private = message.chat.type == "private"
    is_enabled_group_channel = message.chat.id in enabled_chats
    
    if not is_private and not is_enabled_group_channel:
        return
        
    asyncio.create_task(handle_random_reaction(message.chat.id, message.message_id, from_user_id=message.from_user.id))
    parts = message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        return
        
    query = parts[1].strip()
    user_id = message.from_user.id
    
    if user_id not in user_queues:
        user_queues[user_id] = deque()
        user_active_jobs[user_id] = 0
        
    queue = user_queues[user_id]
    
    if len(queue) >= 6:
        return
        
    queue.append((message, query))
    
    if user_active_jobs[user_id] < 2:
        asyncio.create_task(manage_user_queue(user_id))

async def update_percentage(message: types.Message, percentage: int):
    temp_text = f"{percentage}%"
    try:
        await message.edit_text(temp_text)
    except Exception:
        pass

@dp.message()
async def general_message_handler(message: types.Message):
    is_private = message.chat.type == "private"
    is_enabled_group_channel = message.chat.id in enabled_chats
    
    if not is_private and not is_enabled_group_channel:
        return
        
    if message.text:
        asyncio.create_task(handle_random_reaction(message.chat.id, message.message_id, from_user_id=message.from_user.id))
        
        if not message.text.startswith("يوت") and message.text != "ادت" and message.text != "تفعيل" and message.text != "تعطيل":
            welcome_text = "اهلين وياك بوت اليوتيوب تريد اغنيتك\nكول يوت ومن ثم اذكر العنوان"
            
            sent_msg = await message.reply("اهلين")
            asyncio.create_task(handle_random_reaction(sent_msg.chat.id, sent_msg.message_id, is_bot_message=True))
            
            await simulate_parallel_typing(sent_msg, welcome_text)
            
            kb = get_alternating_developer_keyboard(message.from_user.id)
            try:
                await sent_msg.edit_reply_markup(reply_markup=kb)
            except Exception:
                pass
            
            await send_tracked_emoji(message.chat.id, reply_to_id=sent_msg.message_id)

async def on_startup():
    clean_temp_files()
    for dev_id in DEVELOPER_IDS:
        asyncio.create_task(send_startup_notification(dev_id))

async def main():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
