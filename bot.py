import os
import re
import asyncio
import random
import aiohttp
import aiofiles
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, CallbackQuery
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
REACTIONS = ["😘", "😡", "🥰", "🍌", "🍓", "😭", "🤗", "🤣"]

style_channel = "primary"
style_dev_clean = "destructive"
style_dev_error = "destructive"

user_states = {}
last_reactions = {}
bot_audio_messages = {}
song_cache = {}

router = Router()

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

async def send_animated_text(message: Message, full_text: str, reply_markup=None, is_emoji=False):
    words = full_text.split()
    
    if is_emoji and full_text == "🫦":
        msg = await message.reply(
            text="🫦", 
            reply_markup=reply_markup
        )
        asyncio.create_task(add_unique_reaction(msg))
        asyncio.create_task(handle_emoji_animation(msg))
        return msg

    if len(words) <= 3 or is_emoji:
        msg = await message.reply(
            text=full_text, 
            reply_markup=reply_markup
        )
        asyncio.create_task(add_unique_reaction(msg))
        return msg

    chunks = []
    i = 0
    take_three = True
    
    while i < len(words):
        size = 3 if take_three else 2
        chunks.append(" ".join(words[i:i+size]))
        i += size
        take_three = not take_three

    current_text = chunks[0]
    base_msg = await message.reply(
        text=current_text,
        reply_markup=reply_markup
    )
    asyncio.create_task(add_unique_reaction(base_msg))

    for chunk in chunks[1:]:
        await asyncio.sleep(0.3)
        current_text += " " + chunk
        try:
            await base_msg.edit_text(text=current_text, reply_markup=reply_markup)
        except:
            pass

    return base_msg

async def send_dynamic_reply(message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {}).get('chat_state', 0)
    
    asyncio.create_task(add_unique_reaction(message))
    
    if state == 0:
        await send_animated_text(message, "تفضل\nكول يوت ثم اذكر اسم الاغنيه وراح توصلك")
        await send_animated_text(message, "🫦", is_emoji=True)
        user_states[user_id] = {'chat_state': 1}
    else:
        await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك")
        await send_animated_text(message, "🫦", is_emoji=True)
        user_states[user_id] = {'chat_state': 0}

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
    global channel_link, button_name, style_channel, style_dev_clean
    chat_id = message.chat.id
    
    match = re.match(r'^يوت\s+(.+)$', text)
    if not match:
        return

    search_query = match.group(1).strip().lower()
    is_group = message.chat.type in ['group', 'supergroup']
    reply_markup = None
    
    if is_group:
        if channel_link:
            keyboard = [[InlineKeyboardButton(text=button_name, url=channel_link, style=style_channel)]]
        else:
            keyboard = [[InlineKeyboardButton(text="رب العالمين", url=f"tg://user?id={DEV_ID}", style=style_dev_clean)]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if search_query in song_cache:
        try:
            cached_file_id = song_cache[search_query]["file_id"]
            cached_title = song_cache[search_query]["title"]
            
            audio_msg = await message.reply_voice(
                voice=cached_file_id,
                caption=cached_title,
                reply_markup=reply_markup
            )
            asyncio.create_task(add_unique_reaction(audio_msg))
            
            if chat_id not in bot_audio_messages:
                bot_audio_messages[chat_id] = []
            bot_audio_messages[chat_id].append(audio_msg.message_id)
            return
        except:
            keyboard_dev = [[InlineKeyboardButton(text="المطور", url=f"tg://user?id={DEV_ID}", style=style_dev_error)]]
            reply_markup_dev = InlineKeyboardMarkup(inline_keyboard=keyboard_dev)
            await send_animated_text(message, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي", reply_markup=reply_markup_dev)
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
        keyboard_dev = [[InlineKeyboardButton(text="المطور", url=f"tg://user?id={DEV_ID}", style=style_dev_error)]]
        reply_markup_dev = InlineKeyboardMarkup(inline_keyboard=keyboard_dev)
        await send_animated_text(message, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي", reply_markup=reply_markup_dev)
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
            caption=video_title, 
            reply_markup=reply_markup
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

        keyboard_dev = [[InlineKeyboardButton(text="المطور", url=f"tg://user?id={DEV_ID}", style=style_dev_error)]]
        reply_markup_dev = InlineKeyboardMarkup(inline_keyboard=keyboard_dev)
        
        await send_animated_text(message, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي", reply_markup=reply_markup_dev)
        await send_animated_text(message, "🫦", is_emoji=True)
        
        if 'final_filename' in locals() and os.path.exists(final_filename):
            os.remove(final_filename)
        elif 'audio_filename' in locals() and os.path.exists(audio_filename):
            os.remove(audio_filename)

@router.callback_query(F.data == "cancel_action")
async def process_cancel_callback(callback: CallbackQuery):
    if callback.from_user.id != DEV_ID:
        await callback.answer()
        return
    await callback.message.delete()
    await callback.message.answer("صار دادي ماراح اغير او اسوي شي\nءمهمواح")
    await callback.message.answer("🫦")
    await callback.answer()

@router.callback_query(F.data.startswith("select_btn_"))
async def process_btn_select(callback: CallbackQuery):
    if callback.from_user.id != DEV_ID:
        await callback.answer()
        return
    target_btn = callback.data.replace("select_btn_", "")
    
    keyboard = [
        [
            InlineKeyboardButton(text="🟢", callback_data=f"color_{target_btn}_green"),
            InlineKeyboardButton(text="🔴", callback_data=f"color_{target_btn}_destructive"),
            InlineKeyboardButton(text="🔵", callback_data=f"color_{target_btn}_primary")
        ],
        [InlineKeyboardButton(text="إلغاء", callback_data="cancel_action")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        text="اضغط على اللون المطلوب لتعيينه للزر المحدد مولاي:",
        reply_markup=reply_markup
    )
    await callback.answer()

@router.callback_query(F.data.startswith("color_"))
async def process_color_select(callback: CallbackQuery):
    global style_channel, style_dev_clean, style_dev_error
    if callback.from_user.id != DEV_ID:
        await callback.answer()
        return
        
    match = re.match(r'^color_(.+?)_(.+)$', callback.data)
    if not match:
        await callback.answer()
        return
        
    target_btn = match.group(1)
    chosen_color = match.group(2)
    
    if target_btn == "channel":
        style_channel = chosen_color
    elif target_btn == "dev_clean":
        style_dev_clean = chosen_color
    elif target_btn == "dev_error":
        style_dev_error = chosen_color
        
    await callback.message.delete()
    await callback.message.answer("تم تعيين لون الزر المطلوب مثل ماتريد\nمولاي وغصبا عليه اطيعك")
    await callback.message.answer("🫦")
    await callback.answer()

@router.message(F.text)
async def handle_message(message: Message):
    global channel_link, button_name, style_dev_clean
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()
    is_group = message.chat.type in ['group', 'supergroup']
    
    if text == "تنظيف":
        asyncio.create_task(add_unique_reaction(message))
        messages_to_clean = bot_audio_messages.get(chat_id, [])
        deleted_count = 0
        
        for msg_id in messages_to_clean:
            try:
                await message.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                deleted_count += 1
            except:
                pass
                
        bot_audio_messages[chat_id] = []
        
        keyboard = [[InlineKeyboardButton(text="رب العالمين", url=f"tg://user?id={DEV_ID}", style=style_dev_clean)]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await send_animated_text(message, f"تم مسح {deleted_count} من الصوتيات\nلان امرتني مولاي", reply_markup=reply_markup)
        await send_animated_text(message, "🫦", is_emoji=True)
        return

    if text == "ادت":
        if user_id == DEV_ID:
            asyncio.create_task(add_unique_reaction(message))
            keyboard = [
                [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="تغيير اسم الزر")],
                [KeyboardButton(text="تغيير لون الزر")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            await message.reply(
                text="تريد تغير اسم الزر دوس تغيير اسم الزر\nتريد تعين رابط الزر دوس تعيين الرابط\nاو غير ألوان الأزرار الشفافة مولاي",
                reply_markup=reply_markup
            )
            await message.reply(text="🫦")
            return
        else:
            if is_group:
                return
            await send_dynamic_reply(message)
            return

    if user_id == DEV_ID and text == "تغيير لون الزر":
        keyboard = [
            [InlineKeyboardButton(text=button_name, callback_data="select_btn_channel")],
            [InlineKeyboardButton(text="رب العالمين", callback_data="select_btn_dev_clean")],
            [InlineKeyboardButton(text="المطور", callback_data="select_btn_dev_error")],
            [InlineKeyboardButton(text="إلغاء", callback_data="cancel_action")]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await message.reply(
            text="اضغط على اسم الزر التريد تبدل لونه\nعلمود اغيره مثل ماتريد",
            reply_markup=reply_markup
        )
        await message.reply(text="🫦")
        return

    if user_id == DEV_ID and user_id in user_states and 'action' in user_states[user_id]:
        current_action = user_states[user_id].get('action')
        asyncio.create_task(add_unique_reaction(message))
        
        if current_action == 'wait_link':
            is_url = re.match(r'^(https?://)?(t\.me|telegram\.me)/[a-zA-Z0-9_]+/?$', text)
            is_username = re.match(r'^@[a-zA-Z0-9_]+$', text)
            
            if is_url or is_username:
                channel_link = text if not is_username else f"https://t.me/{text[1:]}"
                await send_animated_text(message, "تم تعيين زر الاشتراك العلني تدلل\nءمهمواح")
                await send_animated_text(message, "🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            else:
                await send_animated_text(message, "اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي")
                await send_animated_text(message, "🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            return

        elif current_action == 'wait_name':
            words = text.split()
            if len(words) <= 3:
                button_name = text
                await send_animated_text(message, "غيرت الاسم بدون مشاكل يبعدي انه\nغير يدلل مولاي")
                await send_animated_text(message, "🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            else:
                await send_animated_text(message, "الاسم اطول من المسموح به ثلاث كلمات\nك اقصى طول")
                await send_animated_text(message, "🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            return

    if user_id == DEV_ID:
        if text == "تعيين الرابط":
            asyncio.create_task(add_unique_reaction(message))
            user_states[user_id] = {'action': 'wait_link'}
            await message.reply(
                text="ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", 
                reply_markup=ReplyKeyboardRemove()
            )
            await send_animated_text(message, "🫦", is_emoji=True)
            return
        elif text == "تغيير اسم الزر":
            asyncio.create_task(add_unique_reaction(message))
            user_states[user_id] = {'action': 'wait_name'}
            await message.reply(
                text="شتريد اسم الزر المرفق وي الرسايل\nيصير تاج راسي", 
                reply_markup=ReplyKeyboardRemove()
            )
            await send_animated_text(message, "🫦", is_emoji=True)
            return

    if is_group:
        if text == "بوت":
            await send_dynamic_reply(message)
        elif text.startswith("يوت "):
            asyncio.create_task(add_unique_reaction(message))
            await process_youtube_search(message, text)
        return

    if text.startswith("يوت"):
        asyncio.create_task(add_unique_reaction(message))
        await process_youtube_search(message, text)
        return

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
