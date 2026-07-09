import asyncio
import os
import re
import random
from collections import defaultdict, deque
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties

import STriNGs
import dATAbAse
import MediA
import privATe
import GroUp
from order import order_router, process_whisper_command, track_chat_message

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
    
    if keyboard_markup:
        sent_msg = await message.reply(first_chunk, reply_markup=keyboard_markup)
    else:
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
    return sent_msg

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

user_queues = defaultdict(lambda: asyncio.Queue(maxsize=6))
user_workers = {}

def is_url(text: str) -> bool:
    if re.search(r'(t\.me|youtube\.com|youtu\.be)', text, re.IGNORECASE):
        return False
    regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return bool(re.match(regex, text))

@dp.message(F.content_type.in_({'new_chat_members', 'left_chat_member', 'new_chat_title', 'new_chat_photo', 'delete_chat_photo', 'group_chat_created', 'supergroup_chat_created', 'channel_chat_created', 'migrate_to_chat_id', 'migrate_from_chat_id', 'pinned_message'}))
async def handle_service_messages(message: types.Message):
    await GroUp.handle_group_service_messages(message)

async def user_queue_worker(user_id: int):
    queue = user_queues[user_id]
    while True:
        message, url_text = await queue.get()
        try:
            await MediA.process_download_task(message, url_text, bot, animate_text, trigger_delayed_reaction)
        except Exception:
            pass
        finally:
            queue.task_done()

@dp.message(F.text)
@dp.channel_post(F.text)
async def handle_message(message: types.Message):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))
    track_chat_message(message)

    text = message.text.strip()
    user_id = message.from_user.id if message.from_user else message.chat.id

    if message.chat.type == ChatType.PRIVATE:
        handled = await privATe.handle_private_logic(message, bot, animate_text, trigger_delayed_reaction, safe_send_food_emoji)
        if handled:
            return

    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        handled = await GroUp.handle_group_logic(message, animate_text)
        if handled:
            return

    if is_url(text):
        queue = user_queues[user_id]
        if queue.full():
            await animate_text(message, STriNGs.QUEUE_FULL_MESSAGE)
            return
        await queue.put((message, text))
        if user_id not in user_workers or user_workers[user_id].done():
            user_workers[user_id] = asyncio.create_task(user_queue_worker(user_id))
        return

    if message.chat.type == ChatType.PRIVATE:
        has_english = bool(re.search(r'[a-zA-Z]', text))
        has_russian = bool(re.search(r'[а-яА-Я]', text))
        if (has_english or has_russian) and not (privATe.validate_custom_username(text) and not text.startswith("@")):
            processed_text = privATe.process_custom_languages(text)
            await animate_text(message, processed_text)
            return

        current_index = await dATAbAse.get_user_step(user_id)
        handler_func = STriNGs.RESPONSE_HANDLERS[current_index]
        next_index = (current_index + 1) % len(STriNGs.RESPONSE_HANDLERS)
        await dATAbAse.update_user_step(user_id, next_index)
        await handler_func(message, animate_text)

async def on_startup():
    for admin_id in STriNGs.ALLOWED_DEVELOPERS:
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
    
    dp.message.register(
        lambda msg: process_whisper_command(msg, bot, trigger_delayed_reaction, safe_send_food_emoji),
        lambda msg: any(x in msg.text for x in ["همسة", "همسه", "اهمس", "همس"]) if msg.text else False
    )
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
