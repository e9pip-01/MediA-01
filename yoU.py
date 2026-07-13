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

custom_replies = {}
reply_delay = {}
last_sent_response = {}

class BotStates(StatesGroup):
    waiting_for_lang_input = State()
    waiting_for_trigger = State()
    waiting_for_multi_responses = State()
    waiting_for_sticker_caption = State()

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
    await msg.edit_text(final + "\n\n" + get_next_emoji(), reply_markup=reply_markup)
    return msg

async def trigger_random_reaction(chat_id: int, message_id: int):
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

class DownloadJob:
    def __init__(self, message: Message, query: str):
        self.message = message
        self.query = query
        self.msg_to_edit = None
        self.last_reported_percent = 0

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
            await bot.send_audio(job.message.chat.id, file_cache[url], reply_markup=get_dynamic_developer_button())
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
        
    except:
        await msg.edit_text("الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي", reply_markup=get_dynamic_developer_button())
        for f in os.listdir():
            if f.startswith("temp_"):
                try: os.remove(f)
                except: pass
        user_settings.clear()

async def is_admin(message: Message) -> bool:
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ["creator", "administrator"]

def get_main_reply_keyboard():
    buttons = [
        [InlineKeyboardButton(text="رد متعدد بالستيكرات", callback_data="add_multi_sticker")],
        [InlineKeyboardButton(text="رد متعدد بالنصوص", callback_data="add_multi_text")],
        [InlineKeyboardButton(text="المهلة الزمنية", callback_data="show_delays"), InlineKeyboardButton(text="عرض الردود", callback_data="show_replies")],
        [InlineKeyboardButton(text="مسح", callback_data="delete_panel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
    await send_animated(message.chat.id, "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين", include_dev_btn=True)
    await message.reply("Options:", reply_markup=markup)
    asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id))

@dp.message(F.text.in_(["رد", "اضف رد"]))
async def add_reply_command(message: Message):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return
    
    if message.reply_to_message and message.reply_to_message.sticker:
        sticker = message.reply_to_message.sticker
        raw_cmd = message.text.replace("رد", "").replace("اضف", "").strip()
        
        is_everywhere = "<>" in raw_cmd
        is_start = "><" in raw_cmd
        is_protected = "/ ^" in raw_cmd or "/^" in raw_cmd
        
        trigger = raw_cmd.replace("<>", "").replace("><", "").replace("/ ^", "").replace("/^", "").strip()
        
        if not trigger and message.reply_to_message.text:
            trigger = message.reply_to_message.text
        
        if trigger:
            chat_id = message.chat.id
            if chat_id not in custom_replies:
                custom_replies[chat_id] = []
            
            custom_replies[chat_id].append({
                "trigger": trigger,
                "is_everywhere": is_everywhere,
                "is_start": is_start,
                "is_protected": is_protected,
                "type": "sticker",
                "sticker_file_id": sticker.file_id,
                "responses": [],
                "is_sticker_only": True
            })
            await message.reply("¹# - الرد المضاف هو ملصق\nتدلل يبعدي")
            return

    markup = get_main_reply_keyboard()
    sent_msg = await message.reply("¹# - ازرار الردود المتعددة والمنفردة\nشتفضل بكيفك", reply_markup=markup)
    user_settings[message.from_user.id] = user_settings.get(message.from_user.id, {})
    user_settings[message.from_user.id]['panel_msg_id'] = sent_msg.message_id
    user_settings[message.from_user.id]['cmd_msg_id'] = message.message_id

@dp.callback_query(F.data == "delete_panel")
async def delete_panel_handler(query: CallbackQuery):
    user_data = user_settings.get(query.from_user.id, {})
    cmd_id = user_data.get('cmd_msg_id')
    try:
        await query.message.delete()
        if cmd_id:
            await bot.delete_message(query.message.chat.id, cmd_id)
    except:
        pass

@dp.callback_query(F.data == "show_replies")
async def show_replies_handler(query: CallbackQuery):
    chat_id = query.message.chat.id
    replies = custom_replies.get(chat_id, [])
    if not replies:
        await query.answer("ليس هناك ردود مضافه عزيزي\nاضف رد وسيتم عرض تسمية الرد هنا", show_alert=True)
        return
    
    text_lines = []
    for r in replies:
        syms = ""
        if r["is_everywhere"]:
            syms += " <>"
        elif r["is_start"]:
            syms += " ><"
        if r["is_protected"]:
            syms += " / ^"
        
        text_lines.append(f"{r['trigger']}{syms}")
    
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="عودة", callback_data="back_to_main")]])
    await query.message.edit_text("\n".join(text_lines), reply_markup=markup)

@dp.callback_query(F.data == "show_delays")
async def show_delays_handler(query: CallbackQuery):
    chat_id = query.message.chat.id
    current_val = reply_delay.get(chat_id, 0.1)
    
    def get_style(val):
        return "success" if abs(current_val - val) < 0.01 else "primary"

    buttons = [
        [
            InlineKeyboardButton(text="6.3", callback_data="set_delay_6.3", style=get_style(6.3)),
            InlineKeyboardButton(text="3.6", callback_data="set_delay_3.6", style=get_style(3.6)),
            InlineKeyboardButton(text="1.2", callback_data="set_delay_1.2", style=get_style(1.2))
        ],
        [
            InlineKeyboardButton(text="2.4", callback_data="set_delay_2.4", style=get_style(2.4)),
            InlineKeyboardButton(text="4.2", callback_data="set_delay_4.2", style=get_style(4.2)),
            InlineKeyboardButton(text="2.1", callback_data="set_delay_2.1", style=get_style(2.1))
        ],
        [
            InlineKeyboardButton(text="3.2", callback_data="set_delay_3.2", style=get_style(3.2)),
            InlineKeyboardButton(text="2.3", callback_data="set_delay_2.3", style=get_style(2.3)),
            InlineKeyboardButton(text="4.8", callback_data="set_delay_4.8", style=get_style(4.8))
        ],
        [InlineKeyboardButton(text="عودة", callback_data="back_to_main", style="destructive")]
    ]
    await query.message.edit_text("المهلة الزمنية الفاصة بين كل رسالة ورسالة\nمن الردود اللتي سيرسلها البوت", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("set_delay_"))
async def set_delay_val(query: CallbackQuery):
    val = float(query.data.split("_")[2])
    chat_id = query.message.chat.id
    reply_delay[chat_id] = val
    await show_delays_handler(query)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_handler(query: CallbackQuery):
    markup = get_main_reply_keyboard()
    await query.message.edit_text("¹# - ازرار الردود المتعددة والمنفردة\nشتفضل بكيفك", reply_markup=markup)

@dp.callback_query(F.data == "add_multi_sticker")
async def add_multi_sticker_handler(query: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_trigger)
    await state.update_data(mode="sticker")
    
    cancel_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الغاء", callback_data="cancel_addition")]])
    await query.message.edit_text("¹# - ضيف الرد المتعدد يدعم الستيكرات\nبالكابشن وبدون كابشن", reply_markup=cancel_markup)

@dp.callback_query(F.data == "add_multi_text")
async def add_multi_text_handler(query: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_trigger)
    await state.update_data(mode="text")
    
    cancel_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الغاء", callback_data="cancel_addition")]])
    await query.message.edit_text("¹# - ضيف الرد المتعدد يدعم الستيكرات\nبالكابشن وبدون كابشن", reply_markup=cancel_markup)

@dp.callback_query(F.data == "cancel_addition")
async def cancel_addition_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.delete()

@dp.message(BotStates.waiting_for_trigger)
async def trigger_received(message: Message, state: FSMContext):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return

    text = message.text or ""
    is_everywhere = "<>" in text
    is_start = "><" in text
    is_protected = "/ ^" in text or "/^" in text
    
    trigger = text.replace("<>", "").replace("><", "").replace("/ ^", "").replace("/^", "").strip()
    
    if not trigger:
        await message.reply("¹# - مولاي هاي بعض الرموز وصيغتها اذا تدز\nرد تريده ينعرض بأول الكلمة من النص سوي هذا الرمز\nبعد الكلمة مثال هلو <> اذا بكل مكان بالنص سوي\nهيج >< اذا تريد الرد ممنوع يبوكونه البواكين ضيف بهاي\nالصيغه هذا بعد الرمز ضيف / ثم ^ مثال هلو <> / ^\nاو هلو >< / ^", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الغاء", callback_data="cancel_addition")]]))
        return
        
    await state.update_data(
        trigger=trigger,
        is_everywhere=is_everywhere,
        is_start=is_start,
        is_protected=is_protected,
        responses=[]
    )
    await state.set_state(BotStates.waiting_for_multi_responses)
    await message.reply("¹# - ارسل الردود اللتي تود اضافتها على\nهذا الرد")

@dp.message(BotStates.waiting_for_multi_responses)
async def responses_collect(message: Message, state: FSMContext):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return

    data = await state.get_data()
    mode = data.get("mode")
    responses = data.get("responses", [])
    
    if message.sticker:
        if mode == "text":
            return
        
        sent = await message.reply_sticker(message.sticker.file_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اضف كابشن", callback_data="add_caption_for_sticker")]]))
        await state.update_data(last_sticker_file_id=message.sticker.file_id, last_sticker_msg_id=sent.message_id)
        await state.set_state(BotStates.waiting_for_sticker_caption)
        return
        
    text = message.text
    if text:
        parts = [p.strip() for p in text.split("%") if p.strip()]
        for p in parts:
            responses.append({"type": "text", "content": p})
            
        await state.update_data(responses=responses)
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="نعم", callback_data="add_more_yes"), InlineKeyboardButton(text="لا", callback_data="add_more_no")]
        ])
        await message.reply("¹# - هل تود اضافة المزيد من الردود لهذا الرد\nانقر على زر نعم او لا", reply_markup=markup)

@dp.callback_query(F.data == "add_caption_for_sticker", BotStates.waiting_for_sticker_caption)
async def init_sticker_caption(query: CallbackQuery, state: FSMContext):
    await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="اضف كابشن", callback_data="waiting_caption_active", style="destructive")]]))

@dp.message(BotStates.waiting_for_sticker_caption)
async def sticker_caption_handler(message: Message, state: FSMContext):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return

    data = await state.get_data()
    responses = data.get("responses", [])
    sticker_file_id = data.get("last_sticker_file_id")
    sticker_msg_id = data.get("last_sticker_msg_id")
    
    try:
        await bot.edit_message_reply_markup(message.chat.id, sticker_msg_id, reply_markup=None)
    except:
        pass
        
    caption = message.text
    responses.append({
        "type": "sticker",
        "sticker_file_id": sticker_file_id,
        "caption": caption
    })
    
    await state.update_data(responses=responses)
    await state.set_state(BotStates.waiting_for_multi_responses)
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="نعم", callback_data="add_more_yes"), InlineKeyboardButton(text="لا", callback_data="add_more_no")]
    ])
    await message.reply("¹# - هل تود اضافة المزيد من الردود لهذا الرد\nانقر على زر نعم او لا", reply_markup=markup)

@dp.callback_query(F.data == "add_more_yes", BotStates.waiting_for_multi_responses)
async def add_more_yes_handler(query: CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="عودة", callback_data="return_to_prompt")]])
    await query.message.edit_text("¹# - اضف الرد اللذي تريده ان يدعم\nهذا الرد ايضا", reply_markup=markup)

@dp.callback_query(F.data == "return_to_prompt", BotStates.waiting_for_multi_responses)
async def return_to_prompt_handler(query: CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="نعم", callback_data="add_more_yes"), InlineKeyboardButton(text="لا", callback_data="add_more_no")]
    ])
    await query.message.edit_text("¹# - هل تود اضافة المزيد من الردود لهذا الرد\nانقر على زر نعم او لا", reply_markup=markup)

@dp.callback_query(F.data == "add_more_no", BotStates.waiting_for_multi_responses)
async def add_more_no_handler(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    chat_id = query.message.chat.id
    
    if chat_id not in custom_replies:
        custom_replies[chat_id] = []
        
    custom_replies[chat_id].append({
        "trigger": data.get("trigger"),
        "is_everywhere": data.get("is_everywhere"),
        "is_start": data.get("is_start"),
        "is_protected": data.get("is_protected"),
        "responses": data.get("responses"),
        "type": data.get("mode"),
        "is_sticker_only": False
    })
    
    await state.clear()
    await query.message.edit_text(f"¹# - الرد المضاف هو {data.get('trigger')}\nتدلل يبعدي", reply_markup=None)

@dp.callback_query(F.data == "cancel")
async def cancel_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.delete()
    await bot.send_message(query.message.chat.id, get_next_emoji(), reply_markup=get_dynamic_developer_button())

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
    await bot.send_message(query.message.chat.id, f"تم تبديل لغة وضع اللغات الى\nذكر اللغة {lang_str}", reply_markup=get_dynamic_developer_button())

@dp.message(F.text.startswith("يوت "))
async def youtube_download_router(message: Message):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return
    
    query = message.text.replace("يوت ", "")
    if download_queue.full():
        return
        
    job = DownloadJob(message, query)
    await download_queue.put(job)
    asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id))

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
        await send_animated(message.chat.id, format_text(trans, lang), include_dev_btn=True)
    elif has_other:
        await send_animated(message.chat.id, format_text(text, lang), include_dev_btn=True)
    else:
        trans = translator.translate(text, dest=lang).text
        await send_animated(message.chat.id, format_text(trans, lang), include_dev_btn=True)
        
    asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id))

@dp.message()
async def global_handler(message: Message):
    if message.chat.type in ["group", "supergroup", "channel"] and message.chat.id not in enabled_chats:
        return
        
    chat_id = message.chat.id
    text = message.text
    
    if text:
        replies = custom_replies.get(chat_id, [])
        matched_reply = None
        
        for r in replies:
            trigger = r["trigger"]
            if r["is_everywhere"]:
                if trigger in text:
                    matched_reply = r
                    break
            elif r["is_start"]:
                if text.startswith(trigger):
                    matched_reply = r
                    break
            else:
                if text.strip() == trigger:
                    matched_reply = r
                    break
                    
        if matched_reply:
            delay = reply_delay.get(chat_id, 0.1)
            await asyncio.sleep(delay)
            
            if matched_reply["is_sticker_only"]:
                await message.reply_sticker(matched_reply["sticker_file_id"])
                return
                
            responses = matched_reply["responses"]
            if responses:
                key = f"{chat_id}_{matched_reply['trigger']}"
                history = last_sent_response.get(key, [])
                
                available = [res for res in responses if res not in history]
                if not available:
                    available = responses
                    history = []
                
                chosen = random.choice(available)
                history.append(chosen)
                if len(history) > 2:
                    history.pop(0)
                last_sent_response[key] = history
                
                protect = matched_reply["is_protected"]
                
                if chosen["type"] == "text":
                    await message.reply(chosen["content"], protect_content=protect)
                elif chosen["type"] == "sticker":
                    if chosen.get("caption"):
                        await message.reply_sticker(chosen["sticker_file_id"])
                        await message.reply(chosen["caption"], protect_content=protect)
                    else:
                        await message.reply_sticker(chosen["sticker_file_id"])
            return

    if message.text and not message.text.startswith("يوت ") and message.text != "ادت":
        await send_animated(
            message.chat.id, 
            "اهلين وياك بوت اليوتيوب تريد اغنيتك\nكول يوت ومن ثم اذكر العنوان", 
            include_dev_btn=True
        )
        asyncio.create_task(trigger_random_reaction(message.chat.id, message.message_id))

async def main():
    for _ in range(2):
        asyncio.create_task(process_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
