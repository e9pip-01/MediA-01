import os
import re
import asyncio
import random
import aiohttp
import aiofiles
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import yt_dlp

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass


TOKEN = os.getenv("TELEGRAM_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
DEV_ID = 8597653867


channel_link = None
button_name = "اشترك"
REACTIONS = ["😘", "😡", "🥰", "🍓", "😭", "🤗", "🤣"]


user_states = {}
last_reactions = {}
bot_audio_messages = {}
song_cache = {}

router = Router()


async def add_banana_reaction(message: Message):
    await asyncio.sleep(1.5)
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": "🍌"}])
    except:
        pass


async def add_unique_reaction(message: Message):
    await asyncio.sleep(3)
    chat_id = message.chat.id
    used = last_reactions.get(chat_id, [])
    available = [r for r in REACTIONS if r not in used]
    
    if not available:
        available = REACTIONS.copy()
        used = []
        
    chosen = random.choice(available)
    used.append(chosen)
    if len(used) > 3:
        used.pop(0)
    last_reactions[chat_id] = used
    
    try:
        await message.react(reaction=[{"type": "emoji", "emoji": chosen}])
    except:
        pass


async def handle_emoji_animation(message: Message):
    await asyncio.sleep(3)
    try:
        await message.edit_text("👉🏻🫦")
    except:
        pass


async def send_animated_text(message: Message, full_text: str, reply_markup=None, is_emoji=False, trigger_early_emoji=False):
    if is_emoji and full_text == "🫦":
        msg = await message.reply(text="🫦", reply_markup=reply_markup)
        asyncio.create_task(add_unique_reaction(msg))
        asyncio.create_task(handle_emoji_animation(msg))
        return msg

    lines = full_text.split('\n')
    all_chunks = []
    
    for line in lines:
        words = line.split()
        if not words:
            all_chunks.append("")
            continue
        line_chunks = []
        i = 0
        take_three = True
        while i < len(words):
            size = 3 if take_three else 2
            line_chunks.append(" ".join(words[i:i+size]))
            i += size
            take_three = not take_three
        all_chunks.append(line_chunks)

    total_steps = max(len(chunks) for chunks in all_chunks if chunks)
    
    current_lines = []
    for chunks in all_chunks:
        if chunks:
            current_lines.append(chunks[0])
        else:
            current_lines.append("")
            
    current_text = "\n".join(current_lines)
    base_msg = await message.reply(text=current_text, reply_markup=None)
    asyncio.create_task(add_unique_reaction(base_msg))

    emoji_triggered = False

    for step in range(1, total_steps):
        await asyncio.sleep(0.3)
        current_lines = []
        for chunks in all_chunks:
            if not chunks:
                current_lines.append("")
            else:
                step_index = min(step, len(chunks) - 1)
                current_lines.append(" ".join(chunks[:step_index + 1]))
        
        current_text = "\n".join(current_lines)
        
        try:
            await base_msg.edit_text(text=current_text, reply_markup=None)
        except:
            pass

        if trigger_early_emoji and not emoji_triggered:
            asyncio.create_task(send_animated_text(message, "🫦", is_emoji=True))
            emoji_triggered = True
            
    if trigger_early_emoji and not emoji_triggered:
        asyncio.create_task(send_animated_text(message, "🫦", is_emoji=True))

    return base_msg


async def send_dynamic_reply(message: Message):
    user_id = message.from_user.id
    current_user_state = user_states.get(user_id, {})
    state = current_user_state.get('chat_state', 0)
    
    if state == 0:
        await send_animated_text(message, "تفضل\nكول يوت ثم اذكر اسم الاغنيه وراح توصلك", trigger_early_emoji=True)
        current_user_state['chat_state'] = 1
        user_states[user_id] = current_user_state
    else:
        await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك", trigger_early_emoji=True)
        current_user_state['chat_state'] = 0
        user_states[user_id] = current_user_state


async def search_youtube_api(query):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "maxResults": 1,
        "type": "video",
        "key": YOUTUBE_API_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                res_json = await response.json()
                if "items" in res_json and len(res_json["items"]) > 0:
                    video_id = res_json["items"][0]["id"]["videoId"]
                    video_title = res_json["items"][0]["snippet"]["title"]
                    return f"https://www.youtube.com/watch?v={video_id}", video_title
    except:
        return None, None
    return None, None


def download_video_sync(ydl_opts, video_url):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        video_info = info['entries'][0] if 'entries' in info else info
        return ydl.prepare_filename(video_info)


async def process_youtube_search(message: Message, text: str):
    chat_id = message.chat.id
    
    match = re.match(r'^يوت\s+(.+)$', text)
    if not match:
        return

    search_query = match.group(1).strip().lower()

    if search_query in song_cache:
        try:
            cached_file_id = song_cache[search_query]["file_id"]
            cached_title = song_cache[search_query]["title"]
            
            audio_msg = await message.reply_voice(
                voice=cached_file_id,
                caption=cached_title
            )
            asyncio.create_task(add_unique_reaction(audio_msg))
            
            if chat_id not in bot_audio_messages:
                bot_audio_messages[chat_id] = []
            bot_audio_messages[chat_id].append(audio_msg.message_id)
            return
        except:
            await send_animated_text(message, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي")
            await send_animated_text(message, "🫦", is_emoji=True)
            return

    status_message = await send_animated_text(message, "يتم العثور على الاغنيه مولاي\nماتنتظر فدوا")
    emoji_message = await send_animated_text(message, "🫦", is_emoji=True)

    video_url, video_title = await search_youtube_api(search_query)
    
    if not video_url:
        try:
            await status_message.delete()
            await emoji_message.delete()
        except:
            pass
        await send_animated_text(message, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي")
        await send_animated_text(message, "🫦", is_emoji=True)
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'quiet': True,
        'socket_timeout': 15,
        'http_chunk_size': 1048576,
        'external_downloader': 'curl_cffi',
    }
    
    try:
        loop = asyncio.get_running_loop()
        audio_filename = await loop.run_in_executor(None, download_video_sync, ydl_opts, video_url)
        
        base, ext = os.path.splitext(audio_filename)
        final_filename = f"{base}.ogg"
        
        if os.path.exists(final_filename):
            os.remove(final_filename)
        os.rename(audio_filename, final_filename)

        async with aiofiles.open(final_filename, 'rb') as f:
            voice_data = await f.read()

        from aiogram.types import BufferedInputFile
        input_file = BufferedInputFile(voice_data, filename=final_filename)

        audio_msg = await message.reply_voice(
            voice=input_file, 
            caption=video_title
        )
        asyncio.create_task(add_unique_reaction(audio_msg))
        
        song_cache[search_query] = {
            "file_id": audio_msg.voice.file_id,
            "title": video_title
        }
        
        if chat_id not in bot_audio_messages:
            bot_audio_messages[chat_id] = []
        bot_audio_messages[chat_id].append(audio_msg.message_id)
        
        await status_message.delete()
        await emoji_message.delete()
        os.remove(final_filename)

    except Exception as e:
        try:
            await status_message.delete()
            await emoji_message.delete()
        except:
            pass

        await send_animated_text(message, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي")
        await send_animated_text(message, "🫦", is_emoji=True)
        
        if 'final_filename' in locals() and os.path.exists(final_filename):
            os.remove(final_filename)
        elif 'audio_filename' in locals() and os.path.exists(audio_filename):
            os.remove(audio_filename)


@router.message(F.text)
async def handle_message(message: Message):
    global channel_link, button_name
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()
    is_group = message.chat.type in ['group', 'supergroup']
    is_private = message.chat.type == 'private'
    
    is_admin_or_dev = False
    if user_id == DEV_ID:
        is_admin_or_dev = True
    elif is_group:
        try:
            member = await message.chat.get_member(user_id)
            if member.status in ['administrator', 'creator']:
                is_admin_or_dev = True
        except:
            pass

    is_yut_command = text.startswith("يوت ")

    if is_yut_command:
        if is_private or (is_group and is_admin_or_dev):
            asyncio.create_task(add_banana_reaction(message))
    else:
        if is_private:
            asyncio.create_task(add_unique_reaction(message))
        elif is_group and is_admin_or_dev:
            asyncio.create_task(add_unique_reaction(message))

    current_user_state = user_states.get(user_id, {})
    current_action = current_user_state.get('action')
    
    if is_private and user_id == DEV_ID and text == "الغاء":
        user_states[user_id] = {'chat_state': 0}
        await send_animated_text(message, "صار دادي ماراح اغير او اسوي شي\nءمهمواح", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True)
        return

    if is_private and user_id == DEV_ID and current_action == 'wait_link':
        is_url = re.match(r'^(https?://)?(t\.me|telegram\.me)/[a-zA-Z0-9_]+/?$', text)
        is_username = re.match(r'^@[a-zA-Z0-9_]+$', text)
        
        if is_url or is_username:
            channel_link = text if not is_username else f"https://t.me/{text[1:]}"
            await send_animated_text(message, "تم تعيين زر الاشتراك العلني تدلل\nءمهمواح", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True)
            user_states[user_id] = {'chat_state': 0}
        else:
            await send_animated_text(message, "اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True)
            user_states[user_id] = {'chat_state': 0}
        return

    elif is_private and user_id == DEV_ID and current_action == 'wait_name':
        words = text.split()
        if len(words) <= 3:
            button_name = text
            await send_animated_text(message, "غيرت الاسم بدون مشاكل يبعدي انه\nغير يدلل مولاي", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True)
            user_states[user_id] = {'chat_state': 0}
        else:
            await send_animated_text(message, "الاسم اطول من المسموح به ثلاث كلمات\nك اقصى طول", reply_markup=ReplyKeyboardRemove(), trigger_early_emoji=True)
            user_states[user_id] = {'chat_state': 0}
        return

    if text == "تنظيف":
        if is_admin_or_dev:
            messages_to_clean = bot_audio_messages.get(chat_id, [])
            deleted_count = 0
            
            for msg_id in messages_to_clean:
                try:
                    await message.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    deleted_count += 1
                except:
                    pass
                    
            bot_audio_messages[chat_id] = []
            await send_animated_text(message, f"تم مسح {deleted_count} من الصوتيات\nلان امرتني مولاي", trigger_early_emoji=True)
        return

    if is_private and user_id == DEV_ID and text == "ادت":
        keyboard = [
            [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="تغيير اسم الزر")],
            [KeyboardButton(text="الغاء")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await send_animated_text(
            message=message,
            full_text="تريد تغير اسم الزر دوس تغيير اسم الزر\nتريد تعين رابط الزر دوس تعيين الرابط"
        )
        await send_animated_text(message, "🫦", is_emoji=True, reply_markup=reply_markup)
        return

    if is_private and user_id == DEV_ID:
        if text == "تعيين الرابط":
            user_states[user_id] = {'action': 'wait_link'}
            await send_animated_text(message, "ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", trigger_early_emoji=True)
            return
        elif text == "تغيير اسم الزر":
            user_states[user_id] = {'action': 'wait_name'}
            await send_animated_text(message, "شتريد اسم الزر المرفق وي الرسايل\nيصير تاج راسي", trigger_early_emoji=True)
            return

    if text.startswith("يوت"):
        if is_group and not is_yut_command:
            return
        await process_youtube_search(message, text)
        return

    if is_group:
        if text == "بوت":
            await send_dynamic_reply(message)
        return

    if is_private:
        await send_dynamic_reply(message)


async def main():
    if not TOKEN:
        return

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
