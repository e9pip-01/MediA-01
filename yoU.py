import os
import re
import random
import asyncio
import mimetypes
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from googletrans import Translator
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
translator = Translator()

class BotStates(StatesGroup):
    lang_mode = State()

USER_LANGS = {}
LAST_REACTIONS = {}
LAST_REACTION_TIMES = {}
ACTIVE_GROUPS = set()

REACTIONS_LIST = ["😭", "😘", "🤣", "🥰", "🤗"]
REACTION_TIMES = [2.4, 4.2, 3.2, 2.3, 3.6]

EMOJI_FOODS = ["🥪", "🍣", "🍔", "🥞", "🌭"]
current_food_index = 0

ENGLISH_UPPER = set("ATFGNMUJL")
RUSSIAN_UPPER = set("АИБ")

user_queues = {}
user_active_downloads = {}
active_edit_menus = {}

RANDOM_RESPONSES = [
    "اهلين وياك بوت mيديا تريد اشتغل \nدز رابط وتدلل",
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
    emoji = EMOJI_FOODS[current_food_index % len(EMOJI_FOODS)]
    current_food_index += 1
    msg = await bot.send_message(chat_id=chat_id, text=emoji, reply_to_message_id=reply_to_msg_id)
    asyncio.create_task(set_random_reaction(chat_id, msg.message_id))

def split_text_into_lines_and_chunks(text: str) -> list:
    lines = text.splitlines()
    all_lines_chunks = []
    max_chunks = 0
    
    for line in lines:
        words = line.split()
        chunks = []
        i = 0
        pattern = [3, 2, 3, 1]
        pattern_idx = 0
        while i < len(words):
            take = pattern[pattern_idx % len(pattern)]
            chunk = " ".join(words[i:i+take])
            chunks.append(chunk)
            i += take
            pattern_idx += 1
        all_lines_chunks.append(chunks)
        if len(chunks) > max_chunks:
            max_chunks = len(chunks)
            
    return all_lines_chunks, max_chunks

async def send_animated_text(chat_id: int, text: str, reply_to_id: int = None, send_food: bool = True, reply_markup=None) -> types.Message:
    all_lines_chunks, max_chunks = split_text_into_lines_and_chunks(text)
    
    if max_chunks == 0:
        msg = await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_id)
        if send_food:
            asyncio.create_task(send_next_food_emoji(chat_id, msg.message_id))
        if reply_markup:
            try:
                await msg.edit_reply_markup(reply_markup=reply_markup)
            except:
                pass
        return msg

    current_state_by_line = [""] * len(all_lines_chunks)
    
    for step in range(max_chunks):
        for line_idx, chunks in enumerate(all_lines_chunks):
            if step < len(chunks):
                if current_state_by_line[line_idx]:
                    current_state_by_line[line_idx] += " " + chunks[step]
                else:
                    current_state_by_line[line_idx] = chunks[step]
                    
        frame_text = "\n".join(current_state_by_line)
        
        if step == 0:
            msg = await bot.send_message(chat_id=chat_id, text=frame_text, reply_to_message_id=reply_to_id)
            if send_food:
                asyncio.create_task(send_next_food_emoji(chat_id, msg.message_id))
        else:
            await asyncio.sleep(0.3)
            try:
                await msg.edit_text(frame_text)
            except:
                pass
                
    if reply_markup:
        try:
            await msg.edit_reply_markup(reply_markup=reply_markup)
        except:
            pass
            
    return msg

async def edit_animated_text(msg: types.Message, text: str, send_food: bool = True):
    all_lines_chunks, max_chunks = split_text_into_lines_and_chunks(text)
    
    if max_chunks == 0:
        try:
            await msg.edit_text(text)
        except:
            pass
        if send_food:
            asyncio.create_task(send_next_food_emoji(msg.chat.id, msg.message_id))
        return

    current_state_by_line = [""] * len(all_lines_chunks)
    
    for step in range(max_chunks):
        for line_idx, chunks in enumerate(all_lines_chunks):
            if step < len(chunks):
                if current_state_by_line[line_idx]:
                    current_state_by_line[line_idx] += " " + chunks[step]
                else:
                    current_state_by_line[line_idx] = chunks[step]
                    
        frame_text = "\n".join(current_state_by_line)
        
        try:
            await msg.edit_text(frame_text)
        except:
            pass
            
        if step == 0 and send_food:
            asyncio.create_task(send_next_food_emoji(msg.chat.id, msg.message_id))
            
        if step < max_chunks - 1:
            await asyncio.sleep(0.3)

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

def translate_and_format(text: str, target_lang: str) -> str:
    try:
        translated = translator.translate(text, dest=target_lang).text
        return format_custom_case(translated)
    except:
        return format_custom_case(text)

def has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))

def has_english(text: str) -> bool:
    return bool(re.search(r"[a-zA-Z]", text))

def has_russian(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text))

def build_edit_keyboard(lang_mode_active: bool = False):
    color_lang = "danger" if lang_mode_active else "primary"
    color_switch = "danger" if lang_mode_active else "primary"
    
    buttons = [
        [
            types.InlineKeyboardButton(text="وضع اللغات", callback_data="btn_lang_mode", style=color_lang),
            types.InlineKeyboardButton(text="تبديل اللغة", callback_data="btn_switch_lang", style=color_switch)
        ],
        [
            types.InlineKeyboardButton(text="مسح", callback_data="btn_clear", style="danger")
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

def build_switch_lang_keyboard(selected_lang: str = None):
    color_en = "danger" if selected_lang == "en" else "primary"
    color_ru = "danger" if selected_lang == "ru" else "primary"
    
    buttons = [
        [
            types.InlineKeyboardButton(text="eNG", callback_data="set_lang_en", style=color_en),
            types.InlineKeyboardButton(text="rUS", callback_data="set_lang_ru", style=color_ru)
        ],
        [types.InlineKeyboardButton(text="عودة", callback_data="btn_back", style="primary")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

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
        await send_animated_text(
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
        await send_animated_text(
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

@dp.message(F.chat.type == "private", F.text == "ادت")
async def cmd_edit(message: types.Message, state: FSMContext):
    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    
    current_state = await state.get_state()
    is_active = current_state == BotStates.lang_mode.state
    
    text_reply = (
        "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\n"
        "تريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    )
    
    keyboard = build_edit_keyboard(lang_mode_active=is_active)
    msg = await send_animated_text(message.chat.id, text_reply, message.message_id, send_food=True, reply_markup=keyboard)
    
    chat_id = message.chat.id
    if chat_id not in active_edit_menus:
        active_edit_menus[chat_id] = []
    
    active_edit_menus[chat_id].append((msg.message_id, message.message_id))
    
    if len(active_edit_menus[chat_id]) > 3:
        oldest_msg_id, oldest_cmd_id = active_edit_menus[chat_id].pop(0)
        try:
            await bot.delete_message(chat_id, oldest_msg_id)
        except:
            pass

@dp.callback_query(F.data == "btn_clear")
async def cb_clear(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id
    
    cmd_id = None
    if chat_id in active_edit_menus:
        for idx, (m_id, c_id) in enumerate(active_edit_menus[chat_id]):
            if m_id == msg_id:
                cmd_id = c_id
                active_edit_menus[chat_id].pop(idx)
                break
                
    try:
        await callback.message.delete()
    except:
        pass
        
    if cmd_id:
        try:
            await bot.delete_message(chat_id, cmd_id)
        except:
            pass
            
    await callback.answer()

@dp.callback_query(F.data == "btn_lang_mode")
async def cb_lang_mode(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state == BotStates.lang_mode.state:
        await state.clear()
        keyboard = build_edit_keyboard(lang_mode_active=False)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(
            text="تم تعطيل وضع اللغات\nالوضع ❌",
            show_alert=False
        )
    else:
        await state.set_state(BotStates.lang_mode)
        keyboard = build_edit_keyboard(lang_mode_active=True)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(
            text="تم تفعيل وضع اللغات\nالوضع ✅",
            show_alert=False
        )

@dp.callback_query(F.data == "btn_switch_lang")
async def cb_switch_lang(callback: types.CallbackQuery, state: FSMContext):
    author_id = callback.from_user.id
    current_lang = USER_LANGS.get(author_id, "ru")
    
    text_reply = (
        "تريد تغير لغة وضع اللغات منا\n"
        "اكو زرين عندك"
    )
    markup = build_switch_lang_keyboard(selected_lang=current_lang)
    await callback.message.edit_text(text_reply, reply_markup=markup)

@dp.callback_query(F.data == "btn_back")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    is_active = current_state == BotStates.lang_mode.state
    
    text_reply = (
        "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\n"
        "تريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    )
    keyboard = build_edit_keyboard(lang_mode_active=is_active)
    await callback.message.edit_text(text_reply, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: types.CallbackQuery, state: FSMContext):
    author_id = callback.from_user.id
    lang_code = callback.data.split("_")[2]
    USER_LANGS[author_id] = lang_code
    
    markup = build_switch_lang_keyboard(selected_lang=lang_code)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except:
        pass
    await callback.answer()

@dp.message(BotStates.lang_mode, F.text)
async def process_lang_mode_text(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        return
    
    text = message.text
    if text == "ادت":
        await cmd_edit(message, state)
        return
        
    asyncio.create_task(set_random_reaction(message.chat.id, message.message_id))
    target_lang = USER_LANGS.get(message.from_user.id, "ru")
    
    is_ar = has_arabic(text)
    is_en = has_english(text)
    is_ru = has_russian(text)
    
    if is_ar and not is_en and not is_ru:
        result = translate_and_format(text, target_lang)
    elif (is_en or is_ru) and is_ar:
        result = format_custom_case(text)
    elif is_en or is_ru:
        result = format_custom_case(text)
    else:
        result = translate_and_format(text, target_lang)
        
    await send_animated_text(message.chat.id, result, message.message_id)

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
    base_text = "راح انفذ طلبك مولاي ودامص عيرك العظيم بكل الوضعيات الزانية"
    status_msg = await send_animated_text(
        message.chat.id, 
        base_text, 
        message.message_id,
        send_food=not is_group
    )
    
    last_reported_progress = [0]
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                step = (percent // 25) * 25
                if step > last_reported_progress[0] and step <= 100:
                    last_reported_progress[0] = step
                    new_text = f"{base_text} {step}%"
                    try:
                        asyncio.run_coroutine_threadsafe(
                            status_msg.edit_text(new_text),
                            asyncio.get_event_loop()
                        )
                    except:
                        pass

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook]
    }
    
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
    except Exception:
        await edit_animated_text(status_msg, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", send_food=not is_group)
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
        if Hacker_combined := best_combined:
            selected_formats = [Hacker_combined]
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
        
        uploader_clean = "".join([c for c in uploader if c.isalnum() or c in " -&_ "])
        title_clean = "".join([c for c in title if c.isalnum() or c in " -&"])
        
        if has_arabic(uploader_clean):
            uploader_clean = translate_and_format(uploader_clean, "en")
        else:
            uploader_clean = format_custom_case(uploader_clean)
            
        if has_arabic(title_clean):
            title_clean = translate_and_format(title_clean, "en")
        else:
            title_clean = format_custom_case(title_clean)
            
        uploader_clean = uploader_clean.replace(" ", "_")
        title_clean = " ".join([word for word in title_clean.split() if word != "_"])
        
        rand_suffix = f"_{random.randint(100, 999)}" if len(entries) > 1 else ""
        base_filename = f"{uploader_clean} - {title_clean}{rand_suffix}"
        
        for idx, fmt in enumerate(selected_formats):
            fmt_id = fmt.get('format_id')
            ext = fmt.get('ext', 'mp4')
            
            temp_dl_opts = {
                'format': fmt_id,
                'outtmpl': f'downloads/{base_filename}_temp_{idx}.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [progress_hook]
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
            await status_msg.edit_text(base_text)
        except:
            pass
        await edit_animated_text(status_msg, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", send_food=not is_group)
        return

    try:
        try:
            await status_msg.edit_text(base_text)
        except:
            pass
            
        is_single_video = False
        if len(downloaded_files) == 1:
            mime = downloaded_files[0][1]
            if mime and "video" in mime:
                is_single_video = True
                
        encoded_url = url.replace(":", "%3A").replace("/", "%2F").replace("&", "%26").replace("?", "%3F")
        gif_callback_data = f"gif_{encoded_url}"
        
        gif_keyboard = None
        if is_single_video:
            gif_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="ستيكر GIF", callback_data=gif_callback_data, style="success")]
            ])

        chunk_size = 8
        for i in range(0, len(downloaded_files), chunk_size):
            chunk = downloaded_files[i:i + chunk_size]
            for file_path, mime in chunk:
                file_input = types.FSInputFile(file_path)
                await message.reply_document(
                    document=file_input, 
                    reply_markup=gif_keyboard if is_single_video else None
                )
                try:
                    os.remove(file_path)
                except:
                    pass
            
        await status_msg.delete()
        
        success_msg = await message.reply("نيكني استاهل تشكني اطيعك مثل عديمة الكرامة")
        asyncio.create_task(set_random_reaction(message.chat.id, success_msg.message_id))
    except Exception:
        await edit_animated_text(status_msg, "الرابط غير مدعوم او الموقع مو مدعوم شم كسي ويصير مدعوم ههع امزح دادي", send_food=not is_group)

@dp.callback_query(F.data.startswith("gif_"))
async def cb_gif_download(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    message_id = callback.message.message_id
    
    raw_url = callback.data[4:]
    decoded_url = raw_url.replace("%3A", ":").replace("%2F", "/").replace("%26", "&").replace("%3F", "?")
    
    dev_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="رب العالمين", url="tg://user?id=8467593882", style="danger")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=dev_keyboard)
    except:
        pass
        
    await callback.answer()
    
    progress_msg = await bot.send_message(chat_id=chat_id, text="0%", reply_to_message_id=message_id)
    last_reported_progress = [0]
    
    def gif_progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                step = (percent // 25) * 25
                if step > last_reported_progress[0] and step <= 100:
                    last_reported_progress[0] = step
                    try:
                        asyncio.run_coroutine_threadsafe(
                            progress_msg.edit_text(f"{step}%"),
                            asyncio.get_event_loop()
                        )
                    except:
                        pass

    ydl_opts = {
        'format': 'bestvideo[height<=720]/best',
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [gif_progress_hook]
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
    
    uploader_clean = "".join([c for c in uploader if c.isalnum() or c in " -&_ "])
    title_clean = "".join([c for c in title if c.isalnum() or c in " -&"])
    
    if has_arabic(uploader_clean):
        uploader_clean = translate_and_format(uploader_clean, "en")
    else:
        uploader_clean = format_custom_case(uploader_clean)
        
    if has_arabic(title_clean):
        title_clean = translate_and_format(title_clean, "en")
    else:
        title_clean = format_custom_case(title_clean)
        
    uploader_clean = uploader_clean.replace(" ", "_")
    title_clean = " ".join([word for word in title_clean.split() if word != "_"])
    
    base_filename = f"{uploader_clean} - {title_clean}_gif.mp4"
    file_path = f"downloads/{base_filename}"
    
    os.makedirs("downloads", exist_ok=True)
    
    temp_dl_opts = {
        'format': 'bestvideo[height<=720]/best',
        'outtmpl': file_path,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [gif_progress_hook]
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

    await send_animated_text(
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
            await send_animated_text(
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
