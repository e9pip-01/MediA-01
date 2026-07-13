import os
import asyncio
import random
import re
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from googletrans import Translator

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

translator = Translator()
file_cache = {}
user_settings = {}
enabled_chats = set()

active_downloads = 0
download_queue = asyncio.Queue(maxsize=6)
queue_lock = asyncio.Lock()

emoji_rotation = ["🥪", "🍣", "🍔", "🥞", "🌭", "🐈‍⬛"]
reaction_list = ["😭", "😘", "🤣", "🥰", "🤗"]
emoji_index = 0
button_toggle = True
last_reactions = []

chat_replies = {}
chat_delays = {}
chat_control_panels = {}

class BotStates(StatesGroup):
    waiting_for_lang_input = State()
    waiting_for_trigger = State()
    waiting_for_reply_content = State()
    waiting_for_sticker_caption = State()
    waiting_for_more_decision = State()

class DownloadJob:
    def __init__(self, message: Message, query: str):
        self.message = message
        self.query = query
        self.msg_to_edit = None
        self.last_reported_percent = 0

def format_text(text, lang='en'):
    if lang == 'en':
        keep = ['A', 'T', 'F', 'G', 'N', 'M', 'J', 'L']
        chars = list(text.lower())
        for i, char in enumerate(chars):
            if char.upper() in keep:
                chars[i] = char.upper()
        return "".join(chars)
    elif lang == 'ru':
        keep = ['А', 'И', 'Б']
        chars = list(text.lower())
        for i, char in enumerate(chars):
            if char.upper() in keep:
                chars[i] = char.upper()
        return "".join(chars)
    return text

async def type_text(message: Message, text: str):
    words = text.split()
    current_text = ""
    for i in range(0, len(words), 3):
        chunk = " ".join(words[i:i+3])
        if current_text:
            current_text += " " + chunk
        else:
            current_text = chunk
        try:
            await message.edit_text(current_text)
            await asyncio.sleep(0.3)
        except:
            pass
    return current_text

def get_next_emoji():
    global emoji_index
    emoji = emoji_rotation[emoji_index % len(emoji_rotation)]
    emoji_index += 1
    return emoji

def get_dynamic_developer_button():
    global button_toggle
    if button_toggle:
        text = "تواصل مع المطور"
        url = "tg://user?id=8467593882"
        style = "primary"
    else:
        text = "المطور"
        url = "tg://user?id=8597653867"
        style = "destructive"
    
    button_toggle = not button_toggle
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url, style=style)]])

async def send_animated(chat_id: int, text: str, include_dev_btn: bool = False):
    msg = await bot.send_message(chat_id, ".")
    final = await type_text(msg, text)
    reply_markup = get_dynamic_developer_button() if include_dev_btn else None
    try:
        await msg.edit_text(final, reply_markup=reply_markup)
    except:
        pass
    await bot.send_message(chat_id, get_next_emoji())
    return msg

async def trigger_random_reaction(chat_id: int, message_id: int, message_obj: Message):
    bot_info = await bot.get_me()
    is_bot_msg = message_obj.from_user.id == bot_info.id

    if message_obj.chat.type in ["group", "supergroup", "channel"]:
        if not is_bot_msg:
            try:
                member = await bot.get_chat_member(chat_id, message_obj.from_user.id)
                if member.status != "creator":
                    return
            except:
                return

    global last_reactions
    available = [r for r in reaction_list if r not in last_reactions]
    if not available:
        available = reaction_list
    react = random.choice(available)
    last_reactions.append(react)
    if len(last_reactions) > 4:
        last_reactions.pop(0)
    
    timings = [2.4, 4.2, 3.2, 2.3, 3.6]
    await asyncio.sleep(random.choice(timings))
    try:
        await bot.set_message_reaction(chat_id, message_id, reaction=[{"type": "emoji", "emoji": react}])
    except:
        pass

async def is_admin(message: Message) -> bool:
    if message.chat.type == "private":
        return True
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ["creator", "administrator"]

async def register_panel(chat_id: int, message_id: int):
    if chat_id not in chat_control_panels:
        chat_control_panels[chat_id] = []
    chat_control_panels[chat_id].append(message_id)
    if len(chat_control_panels[chat_id]) > 3:
        old_id = chat_control_panels[chat_id].pop(0)
        try:
            await bot.delete_message(chat_id, old_id)
        except:
            pass

def get_main_reply_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="رد متعدد بالستيكرات", callback_data="add_reply_sticker", style="primary")],
        [InlineKeyboardButton(text="رد متعدد بالنصوص", callback_data="add_reply_text", style="primary")],
        [InlineKeyboardButton(text="المهلة الزمنية", callback_data="delay_settings", style="primary"), InlineKeyboardButton(text="عرض الردود", callback_data="view_replies", style="primary")],
        [InlineKeyboardButton(text="مسح", callback_data="clear_panel", style="destructive")]
    ])

@dp.message(F.text.in_({"رد", "اضف رد"}))
async def add_reply_command(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    
    if message.reply_to_message and message.reply_to_message.sticker:
        await state.update_data(rep_sticker=message.reply_to_message.sticker.file_id)
        await message.reply(
            "¹# - مولاي هاي بعض الرموز وصيغتها اذا تدز\n"
            "رد تريده ينعرض بأول الكلمة من النص سوي هذا الرمز\n"
            "بعد الكلمة مثال هلو <> اذا بكل مكان بالنص سوي\n"
            "هيج >< اذا تريد الرد ممنوع يبوكونه البواكين ضيف بهاي\n"
            "الصيغه هذا بعد الرمز ضيف / ثم ^ مثال هلو <> / ^\n"
            "او هلو >< / ^",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الغاء", callback_data="cancel_silent", style="destructive")]])
        )
        await state.set_state(BotStates.waiting_for_trigger)
        return

    msg = await message.reply("¹# - ازرار الردود المتعددة والمنفردة\nشتفضل بكيفك", reply_markup=get_main_reply_keyboard())
    await register_panel(message.chat.id, msg.message_id)

@dp.message(F.text.startswith("رد ") | F.text.startswith("اضف رد "))
async def fast_reply_add(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    
    cmd_part = "اضف رد " if message.text.startswith("اضف رد ") else "رد "
    trigger_part = message.text.replace(cmd_part, "").strip()
    
    lines = trigger_part.split("\n", 1)
    if len(lines) < 2:
        return
        
    trigger_line = lines[0].strip()
    reply_content = lines[1].strip()
    
    is_anywhere = "<>" in trigger_line
    is_start = "><" in trigger_line
    is_protected = " / ^" in trigger_line
    
    clean_trigger = trigger_line.replace("<>", "").replace("><", "").replace(" / ^", "").strip()
    
    reply_pool = []
    for chunk in reply_content.split("\n%\n"):
        chunk = chunk.strip()
        if chunk:
            reply_pool.append({"type": "text", "content": chunk})
            
    if not reply_pool:
        return
        
    chat_id = message.chat.id
    if chat_id not in chat_replies:
        chat_replies[chat_id] = {}
        
    chat_replies[chat_id][clean_trigger] = {
        "is_anywhere": is_anywhere,
        "is_start": is_start,
        "is_protected": is_protected,
        "pool": reply_pool,
        "last_indices": []
    }
    
    await message.reply(f"¹# - الرد المضاف هو {clean_trigger}\nتدلل يبعدي")

@dp.callback_query(F.data == "cancel_silent")
async def cancel_silent_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await query.message.delete()
    except:
        pass

@dp.callback_query(F.data == "clear_panel")
async def clear_panel_handler(query: CallbackQuery):
    try:
        await query.message.delete()
    except:
        pass

@dp.callback_query(F.data == "add_reply_sticker")
async def add_reply_sticker_btn(query: CallbackQuery, state: FSMContext):
    await state.update_data(mode="sticker", sub_mode="awaiting_trigger")
    await query.message.edit_text(
        "¹# - ضيف الرد المتعدد يدعم الستيكرات\nبالكابشن وبدون كابشن",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الغاء", callback_data="cancel_silent", style="destructive")]])
    )
    await state.set_state(BotStates.waiting_for_trigger)

@dp.callback_query(F.data == "add_reply_text")
async def add_reply_text_btn(query: CallbackQuery, state: FSMContext):
    await state.update_data(mode="text", sub_mode="awaiting_trigger")
    await query.message.edit_text(
        "¹# - ضيف الرد المتعدد يدعم الستيكرات\nبالكابشن وبدون كابشن",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الغاء", callback_data="cancel_silent", style="destructive")]])
    )
    await state.set_state(BotStates.waiting_for_trigger)

@dp.message(BotStates.waiting_for_trigger)
async def process_trigger_input(message: Message, state: FSMContext):
    trigger_text = message.text
    if not trigger_text:
        return
        
    is_anywhere = "<>" in trigger_text
    is_start = "><" in trigger_text
    is_protected = " / ^" in trigger_text
    
    clean_trigger = trigger_text.replace("<>", "").replace("><", "").replace(" / ^", "").strip()
    
    await state.update_data(
        trigger=clean_trigger,
        is_anywhere=is_anywhere,
        is_start=is_start,
        is_protected=is_protected,
        pool=[]
    )
    
    await message.reply("¹# - ارسل الردود اللتي تود اضافتها على\nهذا الرد")
    await state.set_state(BotStates.waiting_for_reply_content)

@dp.message(BotStates.waiting_for_reply_content)
async def process_reply_content(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "sticker")
    
    if message.sticker:
        if mode == "text":
            return
            
        sticker_file_id = message.sticker.file_id
        await state.update_data(current_sticker=sticker_file_id)
        
        buttons = [[InlineKeyboardButton(text="اضف كابشن", callback_data="add_caption_active", style="primary")]]
        await message.reply_sticker(sticker_file_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return
        
    if message.text:
        pool = data.get("pool", [])
        pool.append({"type": "text", "content": message.text})
        await state.update_data(pool=pool)
        
        buttons = [
            [InlineKeyboardButton(text="نعم", callback_data="more_yes"), InlineKeyboardButton(text="لا", callback_data="more_no")]
        ]
        await message.reply("¹# - هل تود اضافة المزيد من الردود لهذا الرد\nانقر على زر نعم او لا", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(BotStates.waiting_for_more_decision)

@dp.callback_query(F.data == "add_caption_active")
async def add_caption_active_callback(query: CallbackQuery, state: FSMContext):
    await query.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اضف كابشن", callback_data="add_caption_active", style="destructive")]])
    )
    await state.set_state(BotStates.waiting_for_sticker_caption)

@dp.message(BotStates.waiting_for_sticker_caption)
async def process_sticker_caption(message: Message, state: FSMContext):
    if not message.text:
        return
        
    data = await state.get_data()
    pool = data.get("pool", [])
    sticker_id = data.get("current_sticker")
    
    if sticker_id:
        pool.append({"type": "sticker", "file_id": sticker_id, "caption": message.text})
        await state.update_data(pool=pool, current_sticker=None)
        
    buttons = [
        [InlineKeyboardButton(text="نعم", callback_data="more_yes"), InlineKeyboardButton(text="لا", callback_data="more_no")]
    ]
    await message.reply("¹# - هل تود اضافة المزيد من الردود لهذا الرد\nانقر على زر نعم او لا", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(BotStates.waiting_for_more_decision)

@dp.callback_query(F.data == "more_yes")
async def more_yes_callback(query: CallbackQuery, state: FSMContext):
    await query.message.edit_text(
        "¹# - اضف الرد اللذي تريده ان يدعم\nهذا الرد ايضا",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="عودة", callback_data="more_back", style="destructive")]])
    )
    await state.set_state(BotStates.waiting_for_reply_content)

@dp.callback_query(F.data == "more_back")
async def more_back_callback(query: CallbackQuery, state: FSMContext):
    buttons = [
        [InlineKeyboardButton(text="نعم", callback_data="more_yes"), InlineKeyboardButton(text="لا", callback_data="more_no")]
    ]
    await query.message.edit_text("¹# - هل تود اضافة المزيد من الردود لهذا الرد\nانقر على زر نعم او لا", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(BotStates.waiting_for_more_decision)

@dp.callback_query(F.data == "more_no")
async def more_no_callback(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    trigger = data.get("trigger")
    pool = data.get("pool", [])
    
    if trigger and pool:
        chat_id = query.message.chat.id
        if chat_id not in chat_replies:
            chat_replies[chat_id] = {}
            
        chat_replies[chat_id][trigger] = {
            "is_anywhere": data.get("is_anywhere", False),
            "is_start": data.get("is_start", False),
            "is_protected": data.get("is_protected", False),
            "pool": pool,
            "last_indices": []
        }
        
    await query.message.edit_text(f"¹# - الرد المضاف هو {trigger}\nتدلل يبعدي")
    await state.clear()

@dp.callback_query(F.data == "delay_settings")
async def delay_settings_callback(query: CallbackQuery):
    chat_id = query.message.chat.id
    current_delay = chat_delays.get(chat_id, 0.1)
    
    buttons_layout = [
        ["6.3", "3.6", "1.2"],
        ["2.4", "4.2", "2.1"],
        ["3.2", "2.3", "4.8"]
    ]
    
    keyboard_buttons = []
    for row in buttons_layout:
        row_buttons = []
        for val in row:
            is_active = (float(val) == current_delay)
            style = "success" if is_active else "primary"
            row_buttons.append(InlineKeyboardButton(text=val, callback_data=f"set_delay_{val}", style=style))
        keyboard_buttons.append(row_buttons)
        
    keyboard_buttons.append([InlineKeyboardButton(text="عودة", callback_data="back_to_main", style="destructive")])
    
    await query.message.edit_text(
        "المهلة الزمنية الفاصلة بين كل رسالة ورسالة\nمن الردود اللتي سيرسلها البوت",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )

@dp.callback_query(F.data.startswith("set_delay_"))
async def set_delay_val_callback(query: CallbackQuery):
    chat_id = query.message.chat.id
    val_str = query.data.split("_")[2]
    new_delay = float(val_str)
    chat_delays[chat_id] = new_delay
    
    buttons_layout = [
        ["6.3", "3.6", "1.2"],
        ["2.4", "4.2", "2.1"],
        ["3.2", "2.3", "4.8"]
    ]
    
    keyboard_buttons = []
    for row in buttons_layout:
        row_buttons = []
        for val in row:
            is_active = (float(val) == new_delay)
            style = "success" if is_active else "primary"
            row_buttons.append(InlineKeyboardButton(text=val, callback_data=f"set_delay_{val}", style=style))
        keyboard_buttons.append(row_buttons)
        
    keyboard_buttons.append([InlineKeyboardButton(text="عودة", callback_data="back_to_main", style="destructive")])
    
    try:
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))
    except:
        pass
    await query.answer()

@dp.callback_query(F.data == "view_replies")
async def view_replies_callback(query: CallbackQuery):
    chat_id = query.message.chat.id
    replies = chat_replies.get(chat_id, {})
    
    if not replies:
        await query.answer("ليس هناك ردود مضافه عزيزي\nاضف رد وسيتم عرض تسمية الرد هنا", show_alert=True)
        return
        
    text_lines = []
    for trigger, meta in replies.items():
        suffix = ""
        if meta["is_anywhere"]:
            suffix += " <>"
        if meta["is_start"]:
            suffix += " ><"
        if meta["is_protected"]:
            suffix += " / ^"
            
        text_lines.append(f"{trigger}{suffix}")
        
    await query.message.edit_text(
        "\n%\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="عودة", callback_data="back_to_main", style="destructive")]])
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(query: CallbackQuery):
    await query.message.edit_text("¹# - ازرار الردود المتعددة والمنفردة\nشتفضل بكيفك", reply_markup=get_main_reply_keyboard())

async def process_queue():
    global active_downloads
    while True:
        job = await download_queue.get()
        async with queue_lock:
            active_downloads += 1
        try:
            await execute_download(job)
        except:
            pass
        finally:
            async with queue_lock:
                active_downloads -= 1
            download_queue.task_done()

async def execute_download(job: DownloadJob):
    def dl_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('max_filesize') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            if total:
                percent = int((downloaded / total) * 100)
                if percent >= job.last_reported_percent + 25 or percent == 100:
                    step = (percent // 25) * 25
                    if step > job.last_reported_percent:
                        job.last_reported_percent = step
                        try:
                            loop = asyncio.get_event_loop()
                            loop.create_task(job.msg_to_edit.edit_text(
                                f"بدءت بالعثور ع\n{job.query}\nانتظر دادي بليز {job.last_reported_percent}%"
                            ))
                        except:
                            pass

    msg = await send_animated(job.message.chat.id, f"بدءت بالعثور ع\n{job.query}\nانتظر دادي بليز 0%")
    job.msg_to_edit = msg
    
    try:
        ydl_opts = {'format': 'bestaudio', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{job.query}", download=False)['entries'][0]
            url = info['webpage_url']
            title = info['title']
            channel = info['uploader']
        
        if url in file_cache:
            sent_cache = await bot.send_audio(job.message.chat.id, file_cache[url], reply_markup=get_dynamic_developer_button())
            asyncio.create_task(trigger_random_reaction(job.message.chat.id, sent_cache.message_id, sent_cache))
            return
        
        ydl_down_opts = {
            'format': 'bestaudio',
            'outtmpl': 'temp_%(id)s.%(ext)s',
            'progress_hooks': [dl_hook],
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(ydl_down_opts) as ydl:
            ydl.download([url])
            filename = [f for f in os.listdir() if f.startswith("temp_")][0]
        
        title_clean = re.sub(r'[^a-zA-Z0-9\s-&]', '', title)
        channel_clean = channel
        
        if re.search(r'[\u0600-\u06FF]', title):
            title_clean = format_text(translator.translate(title_clean, dest='en').text, 'en')
            channel_clean = format_text(translator.translate(channel_clean, dest='en').text, 'en')
        else:
            title_clean = format_text(title_clean, 'en')
            channel_clean = format_text(channel_clean, 'en')

        final_name = f"{channel_clean} - {title_clean}"
        
        from aiogram.types import FSInputFile
        audio_file = FSInputFile(filename, filename=final_name)
        sent = await bot.send_audio(job.message.chat.id, audio_file, title=final_name, reply_markup=get_dynamic_developer_button())
        file_cache[url] = sent.audio.file_id
        
        if os.path.exists(filename):
            os.remove(filename)
        user_settings.clear()
        
        asyncio.create_task(trigger_random_reaction(job.message.chat.id, sent.message_id, sent))
        
    except:
        err_msg = await msg.edit_text("الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي", reply_markup=get_dynamic_developer_button())
        asyncio.create_task(trigger_random_reaction(job.message.chat.id, err_msg.message_id, err_msg))
        for f in os.listdir():
            if f.startswith("temp_"):
                try: os.remove(f)
                except: pass
        user_settings.clear()

@dp.message(F.chat.type.in_(["group", "supergroup", "channel"]), F.text == "تفعيل")
async def enable_chat(message: Message):
    if await is_admin(message):
        enabled_chats.add(message.chat.id)
        await message.reply("¹# - تم تفعيل اليوت مولاي\nاليوتيوب شغال")

@dp.message(F.chat.type.in_(["group", "supergroup", "channel"]), F.text == "تعطيل")
async def disable_chat(message: Message):
    if await is_admin(message):
        if message.chat.id in enabled_chats:
            enabled_chats.remove(message.chat.id)
        await message.reply("¹# - تم تعطيل اليوت مولاي\nاليوتيوب معطل")

@dp.message(F.chat.type == "private", F.text == "ادت")
async def edit_cmd(message: Message):
    buttons = [
        [InlineKeyboardButton(text="وضع اللغات", callback_data="lang_mode"), InlineKeyboardButton(text="تبديل اللغة", callback_data="switch_lang")],
        [InlineKeyboardButton(text="الغاء", callback_data="cancel")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    animated_msg = await send_animated(message.chat.id, "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين", include_dev_btn=True)
    await message.reply("Options:", reply_markup=markup)
    
    asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id, message))
    asyncio.create_task(trigger_random_reaction(message.chat.id, animated_msg.message_id, animated_msg))

@dp.callback_query(F.data == "cancel")
async def cancel_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.delete()
    sent_msg = await bot.send_message(query.message.chat.id, get_next_emoji(), reply_markup=get_dynamic_developer_button())
    asyncio.create_task(trigger_random_reaction(query.message.chat.id, sent_msg.message_id, sent_msg))

@dp.callback_query(F.data == "lang_mode")
async def lang_mode_handler(query: CallbackQuery, state: FSMContext):
    user_settings[query.from_user.id] = user_settings.get(query.from_user.id, {})
    user_settings[query.from_user.id]['active'] = True
    await state.set_state(BotStates.waiting_for_lang_input)
    await query.answer("تم تفعيل وضع اللغات")

@dp.callback_query(F.data == "switch_lang")
async def switch_lang_handler(query: CallbackQuery):
    buttons = [[InlineKeyboardButton(text="انكليزية", callback_data="set_en"), InlineKeyboardButton(text="روسية", callback_data="set_ru")]]
    await query.message.edit_text("تغيير اللغة", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("set_"))
async def set_lang_handler(query: CallbackQuery):
    lang = query.data.split("_")[1]
    user_settings[query.from_user.id] = user_settings.get(query.from_user.id, {})
    user_settings[query.from_user.id]['lang'] = lang
    await query.message.delete()
    lang_str = "الروسية" if lang == "ru" else "الانكليزية"
    sent_msg = await bot.send_message(query.message.chat.id, f"تم تبديل لغة وضع اللغات الى\nذكر اللغة {lang_str}", reply_markup=get_dynamic_developer_button())
    asyncio.create_task(trigger_random_reaction(query.message.chat.id, sent_msg.message_id, sent_msg))

@dp.message(F.text.startswith("يوت "))
async def youtube_download_router(message: Message):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return
    
    query = message.text.replace("يوت ", "")
    if download_queue.full():
        return
        
    job = DownloadJob(message, query)
    await download_queue.put(job)
    asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id, message))

@dp.message(BotStates.waiting_for_lang_input)
async def lang_input_handler(message: Message):
    if message.chat.type != "private":
        return
    text = message.text
    lang = user_settings.get(message.from_user.id, {}).get('lang', 'en')
    has_ar = bool(re.search(r'[\u0600-\u06FF]', text))
    has_other = bool(re.search(r'[a-zA-Zа-яА-Я]', text))
    
    if has_ar and not has_other:
        trans = translator.translate(text, dest=lang).text
        animated_msg = await send_animated(message.chat.id, format_text(trans, lang), include_dev_btn=True)
    elif has_other:
        animated_msg = await send_animated(message.chat.id, format_text(text, lang), include_dev_btn=True)
    else:
        trans = translator.translate(text, dest=lang).text
        animated_msg = await send_animated(message.chat.id, format_text(trans, lang), include_dev_btn=True)
        
    asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id, message))
    asyncio.create_task(trigger_random_reaction(message.chat.id, animated_msg.message_id, animated_msg))

@dp.message()
async def global_handler(message: Message):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return

    chat_id = message.chat.id
    text = message.text
    
    if text:
        replies = chat_replies.get(chat_id, {})
        matched_reply = None
        
        for trigger, meta in replies.items():
            if meta["is_anywhere"] and trigger in text:
                matched_reply = meta
                break
            elif meta["is_start"] and text.startswith(trigger):
                matched_reply = meta
                break
            elif not meta["is_anywhere"] and not meta["is_start"] and text == trigger:
                matched_reply = meta
                break
                
        if matched_reply:
            pool = matched_reply["pool"]
            last_indices = matched_reply["last_indices"]
            
            available_indices = [idx for idx in range(len(pool)) if idx not in last_indices]
            if not available_indices:
                available_indices = list(range(len(pool)))
                
            chosen_idx = random.choice(available_indices)
            last_indices.append(chosen_idx)
            if len(last_indices) > 2:
                last_indices.pop(0)
                
            reply_item = pool[chosen_idx]
            delay = chat_delays.get(chat_id, 0.1)
            
            await asyncio.sleep(delay)
            
            if reply_item["type"] == "text":
                sent_reply = await message.reply(reply_item["content"])
                asyncio.create_task(trigger_random_reaction(chat_id, sent_reply.message_id, sent_reply))
            elif reply_item["type"] == "sticker":
                if reply_item.get("caption"):
                    sent_sticker = await message.reply_sticker(reply_item["file_id"])
                    await asyncio.sleep(delay)
                    sent_caption = await message.reply(reply_item["caption"])
                    asyncio.create_task(trigger_random_reaction(chat_id, sent_sticker.message_id, sent_sticker))
                    asyncio.create_task(trigger_random_reaction(chat_id, sent_caption.message_id, sent_caption))
                else:
                    sent_sticker = await message.reply_sticker(reply_item["file_id"])
                    asyncio.create_task(trigger_random_reaction(chat_id, sent_sticker.message_id, sent_sticker))
            return

    if message.text and not message.text.startswith("يوت ") and message.text != "ادت":
        animated_msg = await send_animated(
            message.chat.id, 
            "اهلين وياك بوت اليوتيوب تريد اغنيتك\nكول يوت ومن ثم اذكر العنوان", 
            include_dev_btn=True
        )
        asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id, message))
        asyncio.create_task(trigger_random_reaction(message.chat.id, animated_msg.message_id, animated_msg))

async def main():
    for _ in range(2):
        asyncio.create_task(process_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    