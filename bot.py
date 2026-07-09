import asyncio
import os
import re
import time
import random
import string
from collections import defaultdict, deque
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties
from yt_dlp import YoutubeDL

import STriNGs
import dATAbAse
from order import order_router, process_whisper_command, process_whisper_input, handle_start_whisper_session

TOKEN = os.getenv("BOT_TOKEN")

recent_reactions = deque(maxlen=4)
recent_delays = deque(maxlen=4)
emoji_lock = asyncio.Lock()
processed_food_messages = set()

def get_unique_reaction() -> str:
    available = [e for e in STriNGs.REACTION_EMOJIS if e not in recent_reactions]
    chosen = random.choice(available if available else STriNGs.REACTION_EMOJIS)
    recent_reactions.append(chosen)
    return chosen

def get_unique_delay() -> float:
    available = [d for d in STriNGs.REACTION_DELAYS if d not in recent_delays]
    chosen = random.choice(available if available else STriNGs.REACTION_DELAYS)
    recent_delays.append(chosen)
    return chosen

async def trigger_delayed_reaction(bot_instance: Bot, chat_id: int, message_id: int):
    try:
        delay = get_unique_delay()
        reaction_emoji = get_unique_reaction()
        await asyncio.sleep(delay)
        await bot_instance.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[types.ReactionTypeEmoji(emoji=reaction_emoji)]
        )
    except Exception:
        pass

async def safe_send_food_emoji(chat_id: int, trigger_msg_id: int):
    try:
        async with emoji_lock:
            task_key = f"{chat_id}_{trigger_msg_id}"
            if task_key in processed_food_messages:
                return
            processed_food_messages.add(task_key)
            
            if len(processed_food_messages) > 200:
                processed_food_messages.clear()
                processed_food_messages.add(task_key)

        await asyncio.sleep(1.2)
        async with emoji_lock:
            idx = await dATAbAse.get_next_emoji_index()
            emoji = STriNGs.FOOD_EMOJIS[idx]
            sent = await bot.send_message(chat_id=chat_id, text=emoji)
            asyncio.create_task(trigger_delayed_reaction(bot, sent.chat.id, sent.message_id))
    except Exception:
        pass

async def animate_text(message: types.Message, text: str, reply_markup: types.InlineKeyboardMarkup = None, keyboard_markup: types.ReplyKeyboardMarkup = None):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))

    lines = text.split('\n')
    parsed_lines = [line.split() for line in lines]
    
    line_indices = [0] * len(lines)
    line_toggles = [True] * len(lines)
    line_active = [False] * len(lines)
    
    if parsed_lines:
        line_active[0] = True

    first_chunk = " ".join(parsed_lines[0][0:3])
    line_indices[0] = 3
    line_toggles[0] = False
    
    sent_msg = await message.reply(first_chunk)
    asyncio.create_task(trigger_delayed_reaction(bot, sent_msg.chat.id, sent_msg.message_id))
    await asyncio.sleep(0.3)

    while True:
        all_done = True
        for idx in range(len(lines)):
            if line_indices[idx] < len(parsed_lines[idx]):
                all_done = False
                break
        if all_done:
            break

        current_display_lines = []
        
        for idx in range(len(lines)):
            words = parsed_lines[idx]
            
            if line_active[idx] and line_indices[idx] < len(words):
                take = 3 if line_toggles[idx] else 2
                line_toggles[idx] = not line_toggles[idx]
                line_indices[idx] += take
                
                if idx + 1 < len(lines) and not line_active[idx + 1]:
                    line_active[idx + 1] = True

            current_line_text = " ".join(words[:line_indices[idx]])
            if current_line_text or idx < len(lines) - 1:
                current_display_lines.append(current_line_text)

        full_current_text = "\n".join(current_display_lines)
        
        try:
            await sent_msg.edit_text(full_current_text)
            await asyncio.sleep(0.3)
        except Exception:
            pass

    try:
        await sent_msg.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass

    asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

user_queues = defaultdict(lambda: asyncio.Queue(maxsize=6))
user_workers = {}

def cleanup_stale_files():
    downloads_dir = 'downloads'
    if not os.path.exists(downloads_dir):
        return
    now = time.time()
    for filename in os.listdir(downloads_dir):
        file_path = os.path.join(downloads_dir, filename)
        if os.path.isfile(file_path):
            if now - os.path.getmtime(file_path) > 3600:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

def clean_filename_part(text: str) -> str:
    if not text:
        return ""
    
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9\s\-&]', '', text)
    cleaned = ' '.join(cleaned.split())
    
    result = []
    for char in cleaned:
        if char.isalpha():
            if char in 'ftanmjutFTANMJUT':
                result.append(char.upper())
            elif char in 'абиАБИ':
                result.append(char.upper())
            else:
                result.append(char.lower())
        else:
            result.append(char)
            
    return "".join(result).strip()

def generate_smart_filename(uploader: str) -> str:
    clean_uploader = clean_filename_part(uploader)
    if not clean_uploader:
        clean_uploader = "ANoNyMoUs"
        
    random_digits = "".join(random.choices(string.digits, k=9))
    return f"{clean_uploader} - {random_digits}"

def is_url(text: str) -> bool:
    if re.search(r'(t\.me|youtube\.com|youtu\.be)', text, re.IGNORECASE):
        return False
    regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return bool(re.match(regex, text))

def process_custom_languages(text: str) -> str:
    result = []
    for char in text:
        if char.isalpha():
            if char in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                if char.lower() in ['a', 'f', 't', 'u', 'g', 'n', 'm', 'j']:
                    result.append(char.upper())
                else:
                    result.append(char.lower())
            elif char in 'عبدفغهخحجكمنتبالبيسشظزوةىلارؤءئإلأآلإ':
                if char.lower() in ['а', 'и', 'б']:
                    result.append(char.upper())
                else:
                    result.append(char.lower())
            else:
                result.append(char)
        else:
            result.append(char)
    return "".join(result)

def validate_custom_username(text: str) -> bool:
    clean = text.replace("@", "").strip()
    if not clean:
        return False
    if clean[0].isdigit() or clean[0] == '-' or clean[-1] == '-':
        return False
    if not re.match(r'^[a-zA-Z0-9_\-]+$', clean):
        return False
    return True

async def check_force_subscription(user_id: int) -> bool:
    link = await dATAbAse.get_force_sub_link()
    if not link:
        return True
    chat_identifier = link
    if "t.me/" in link:
        parts = link.split("t.me/")
        if len(parts) > 1:
            chat_identifier = f"@{parts[1].split('/')[0]}"
    else:
        if not chat_identifier.startswith("@"):
            chat_identifier = f"@{chat_identifier}"
    try:
        member = await bot.get_chat_member(chat_id=chat_identifier, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception:
        return False

async def process_download_task(message: types.Message, url_text: str):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))
    user_id = message.from_user.id if message.from_user else message.chat.id
    
    cached_ids = await dATAbAse.get_cached_file_ids(url_text)
    if cached_ids:
        try:
            chunks = [cached_ids[i:i + 8] for i in range(0, len(cached_ids), 8)]
            for chunk in chunks:
                media_group = []
                for fid in chunk:
                    media_group.append(types.InputMediaDocument(media=fid))
                
                if len(media_group) == 1:
                    sent = await message.reply_document(media_group[0].media)
                    asyncio.create_task(trigger_delayed_reaction(bot, sent.chat.id, sent.message_id))
                else:
                    sent_group = await message.reply_media_group(media=media_group)
                    if sent_group:
                        asyncio.create_task(trigger_delayed_reaction(bot, sent_group[0].chat.id, sent_group[0].message_id))

            sent_succ = await message.reply(STriNGs.SUCCESS_MESSAGE)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_succ.chat.id, sent_succ.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
            return
        except Exception:
            pass

    cleanup_stale_files()
    progress_msg = await message.reply(STriNGs.PROGRESS_START)
    asyncio.create_task(trigger_delayed_reaction(bot, progress_msg.chat.id, progress_msg.message_id))
    last_reported_progress = 0
    downloaded_files = []
    
    loop = asyncio.get_running_loop()

    def ytdl_hook(d):
        nonlocal last_reported_progress
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                if percent > 10 and percent >= last_reported_progress + 20:
                    last_reported_progress = (percent // 20) * 20
                    asyncio.run_coroutine_threadsafe(
                        progress_msg.edit_text(STriNGs.PROGRESS_TEMPLATE.format(percent=last_reported_progress)),
                        loop
                    )

    ydl_opts = {
        'format': 'best',
        'progress_hooks': [ytdl_hook],
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False
    }
    
    try:
        ydl = YoutubeDL(ydl_opts)
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url_text, download=False))
        
        uploader = info.get('uploader') or info.get('channel') or "ANoNyMoUs"
        
        entries = []
        if 'entries' in info and info['entries']:
            entries = [e for e in info['entries'] if e]
        else:
            entries = [info]
            
        for entry in entries:
            custom_name = generate_smart_filename(uploader)
            entry_opts = {
                'format': 'best',
                'outtmpl': f'downloads/{custom_name}.%(ext)s',
                'quiet': True,
                'no_warnings': True
            }
            entry_info = await loop.run_in_executor(None, lambda: YoutubeDL(entry_opts).extract_info(entry.get('webpage_url') or url_text, download=True))
            filename = YoutubeDL(entry_opts).prepare_filename(entry_info)
            if os.path.exists(filename):
                downloaded_files.append(filename)

        await progress_msg.delete()
        
        if downloaded_files:
            chunks = [downloaded_files[i:i + 8] for i in range(0, len(downloaded_files), 8)]
            uploaded_file_ids = []
            
            for chunk in chunks:
                media_group = []
                for filepath in chunk:
                    file_input = types.FSInputFile(filepath)
                    media_group.append(types.InputMediaDocument(media=file_input))
                
                if len(media_group) == 1:
                    sent_doc = await message.reply_document(media_group[0].media)
                    uploaded_file_ids.append(sent_doc.document.file_id)
                    asyncio.create_task(trigger_delayed_reaction(bot, sent_doc.chat.id, sent_doc.message_id))
                else:
                    sent_group = await message.reply_media_group(media=media_group)
                    if sent_group:
                        asyncio.create_task(trigger_delayed_reaction(bot, sent_group[0].chat.id, sent_group[0].message_id))
                    for sent_msg in sent_group:
                        if sent_msg.document:
                            uploaded_file_ids.append(sent_msg.document.file_id)
            
            if uploaded_file_ids:
                await dATAbAse.save_cached_file_ids(url_text, uploaded_file_ids)
                
            sent_final = await message.reply(STriNGs.SUCCESS_MESSAGE)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_final.chat.id, sent_final.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        else:
            sent_err = await message.reply(STriNGs.FILE_NOT_FOUND)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_err.chat.id, sent_err.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
            
    except Exception:
        try:
            await progress_msg.edit_text(STriNGs.ERROR_MESSAGE)
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        except Exception:
            pass
    finally:
        for filepath in downloaded_files:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

async def user_queue_worker(user_id: int):
    queue = user_queues[user_id]
    while True:
        message, url_text = await queue.get()
        try:
            await process_download_task(message, url_text)
        except Exception:
            pass
        finally:
            queue.task_done()

@dp.message(F.content_type.in_({'new_chat_members', 'left_chat_member', 'new_chat_title', 'new_chat_photo', 'delete_chat_photo', 'group_chat_created', 'supergroup_chat_created', 'channel_chat_created', 'migrate_to_chat_id', 'migrate_from_chat_id', 'pinned_message'}))
async def handle_service_messages(message: types.Message):
    status = await dATAbAse.get_notification_status(message.chat.id)
    if status == 1:
        try:
            await message.delete()
        except Exception:
            pass

@dp.message(F.text)
@dp.channel_post(F.text)
async def handle_message(message: types.Message):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))
    
    text = message.text.strip()
    user_id = message.from_user.id if message.from_user else message.chat.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    
    is_group_or_channel = chat_type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]

    if chat_type == ChatType.PRIVATE and text.startswith("/start whsp_"):
        payload = text.split("/start ")[1]
        await handle_start_whisper_session(message, payload, bot, trigger_delayed_reaction, safe_send_food_emoji)
        return

    if chat_type == ChatType.PRIVATE:
        whisper_processed = await process_whisper_input(message, bot, trigger_delayed_reaction, safe_send_food_emoji)
        if whisper_processed:
            return

    current_admin_state = await dATAbAse.get_admin_state(user_id)
    if current_admin_state == "wait_link" and await STriNGs.is_user_allowed_for_edit(message):
        is_link_input = text.startswith("http://") or text.startswith("https://") or "t.me/" in text
        is_user_input = text.startswith("@") or validate_custom_username(text)
        
        if is_link_input or is_user_input:
            await dATAbAse.set_force_sub_link(text)
            await dATAbAse.set_admin_state(user_id, "none")
            sent_ok = await message.reply(STriNGs.SET_LINK_SUCCESS_MSG, reply_markup=types.ReplyKeyboardRemove())
            asyncio.create_task(trigger_delayed_reaction(bot, sent_ok.chat.id, sent_ok.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        else:
            await dATAbAse.set_admin_state(user_id, "none")
            sent_fail = await message.reply(STriNGs.INVALID_LINK_MSG, reply_markup=types.ReplyKeyboardRemove())
            asyncio.create_task(trigger_delayed_reaction(bot, sent_fail.chat.id, sent_fail.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        return

    if text == "ادت البوت":
        if chat_type == ChatType.PRIVATE and user_id in [8467593882, 8597653867]:
            sent_pnl = await message.reply(STriNGs.BOT_EDIT_PANEL_MSG, reply_markup=STriNGs.get_bot_edit_keyboard())
            asyncio.create_task(trigger_delayed_reaction(bot, sent_pnl.chat.id, sent_pnl.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
            return

    if text == STriNGs.BTN_SET_LINK:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_admin_state(user_id, "wait_link")
            sent_ask = await message.reply(STriNGs.ASK_LINK_MSG)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_ask.chat.id, sent_ask.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        return

    if text == STriNGs.BTN_SHOW_MSG:
        if await STriNGs.is_user_allowed_for_edit(message):
            current_link = await dATAbAse.get_force_sub_link()
            inline_kb = await STriNGs.get_force_sub_inline(current_link)
            sent_show = await message.reply(STriNGs.FORCE_SUB_TEXT, reply_markup=inline_kb)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_show.chat.id, sent_show.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        return

    if chat_type == ChatType.PRIVATE and not await check_force_subscription(user_id):
        current_link = await dATAbAse.get_force_sub_link()
        inline_kb = await STriNGs.get_force_sub_inline(current_link)
        sent_sub = await message.reply(STriNGs.FORCE_SUB_TEXT, reply_markup=inline_kb)
        asyncio.create_task(trigger_delayed_reaction(bot, sent_sub.chat.id, sent_sub.message_id))
        asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        return

    if text.lower() == "ادت":
        if is_group_or_channel:
            try:
                member = await message.chat.get_member(user_id)
                if member.status in ['creator', 'administrator']:
                    sent_edit = await message.reply(STriNGs.PANEL_TITLE_MSG, reply_markup=STriNGs.get_keyboard_markup(user_id))
                    asyncio.create_task(trigger_delayed_reaction(bot, sent_edit.chat.id, sent_edit.message_id))
                    asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
                    return
            except Exception:
                pass

    if text == STriNGs.BTN_MUTE:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_notification_status(chat_id, 1)
            await animate_text(message, STriNGs.MUTE_SUCCESS_MSG)
            return

    if text == STriNGs.BTN_UNMUTE:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_notification_status(chat_id, 0)
            await animate_text(message, STriNGs.UNMUTE_SUCCESS_MSG)
            return

    if text == "الغاء":
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_admin_state(user_id, "none")
            sent_resp = await message.reply(STriNGs.CANCEL_SUCCESS_MSG, reply_markup=types.ReplyKeyboardRemove())
            asyncio.create_task(trigger_delayed_reaction(bot, sent_resp.chat.id, sent_resp.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        return

    if is_url(text):
        queue = user_queues[user_id]
        if queue.full():
            sent_q = await message.reply(STriNGs.QUEUE_FULL_MESSAGE)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_q.chat.id, sent_q.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
            return
        await queue.put((message, text))
        if user_id not in user_workers or user_workers[user_id].done():
            user_workers[user_id] = asyncio.create_task(user_queue_worker(user_id))
        return

    has_english = bool(re.search(r'[a-zA-Z]', text))
    has_russian = bool(re.search(r'[а-яА-Я]', text))
    
    if (has_english or has_russian) and not (validate_custom_username(text) and not text.startswith("@")):
        processed_text = process_custom_languages(text)
        sent_custom = await message.reply(processed_text)
        asyncio.create_task(trigger_delayed_reaction(bot, sent_custom.chat.id, sent_custom.message_id))
        asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        return

    if is_group_or_channel:
        if text == "بوت":
            current_index = await dATAbAse.get_user_step(user_id)
            handler_func = STriNGs.RESPONSE_HANDLERS[current_index]
            next_index = (current_index + 1) % len(STriNGs.RESPONSE_HANDLERS)
            await dATAbAse.update_user_step(user_id, next_index)
            await handler_func(message, animate_text)
    else:
        current_index = await dATAbAse.get_user_step(user_id)
        handler_func = STriNGs.RESPONSE_HANDLERS[current_index]
        next_index = (current_index + 1) % len(STriNGs.RESPONSE_HANDLERS)
        await dATAbAse.update_user_step(user_id, next_index)
        await handler_func(message, animate_text)

async def on_startup():
    for admin_id in [STriNGs.DEVELOPER_ID, STriNGs.SUPPORT_ID]:
        try:
            sent_start = await bot.send_message(chat_id=admin_id, text=STriNGs.STARTUP_MESSAGE)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_start.chat.id, sent_start.message_id))
            asyncio.create_task(safe_send_food_emoji(int(admin_id), sent_start.message_id))
        except Exception:
            pass

async def main():
    await dATAbAse.init_db()
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    await on_startup()
    
    dp.include_router(order_router)
    
    dp.callback_query.register(
        lambda cb: handle_inline_buttons(cb, bot, trigger_delayed_reaction, safe_send_food_emoji, handle_message),
        F.data.startswith("btn_")
    )
    dp.message.register(
        lambda msg: process_whisper_command(msg, bot, trigger_delayed_reaction, safe_send_food_emoji),
        lambda msg: any(x in msg.text for x in ["همسة", "همسه", "اهمس", "همس"]) if msg.text else False
    )
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
