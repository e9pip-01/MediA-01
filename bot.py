import os
import re
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import yt_dlp

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

TOKEN = os.getenv("TELEGRAM_TOKEN")
DEV_ID = 8597653867

user_states = {}
channel_link = None
button_name = "اشترك"

REACTIONS = ["😘", "😡", "🥰", "🍌", "🍓", "😭", "🤗", "🤣"]
last_reactions = {}
bot_audio_messages = {}

async def add_unique_reaction(message, chat_id):
    await asyncio.sleep(3)
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
        await message.set_reaction(reaction=chosen)
    except:
        pass

async def handle_emoji_animation(message, chat_id):
    await asyncio.sleep(3)
    try:
        await message.edit_text("👉🏻🫦")
    except:
        pass

async def send_animated_text(update: Update, context: ContextTypes.DEFAULT_TYPE, full_text: str, reply_markup=None, is_emoji=False):
    chat_id = update.message.chat_id
    words = full_text.split()
    
    if len(words) <= 3 or is_emoji:
        msg = await update.message.reply_text(
            full_text, 
            reply_markup=reply_markup,
            reply_to_message_id=update.message.message_id
        )
        asyncio.create_task(add_unique_reaction(msg, chat_id))
        if is_emoji and full_text == "👉🏻🫦":
            asyncio.create_task(handle_emoji_animation(msg, chat_id))
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
    base_msg = await update.message.reply_text(
        current_text,
        reply_markup=reply_markup,
        reply_to_message_id=update.message.message_id
    )
    asyncio.create_task(add_unique_reaction(base_msg, chat_id))

    for chunk in chunks[1:]:
        await asyncio.sleep(0.3)
        current_text += " " + chunk
        try:
            await base_msg.edit_text(current_text, reply_markup=reply_markup)
        except:
            pass

    return base_msg

async def send_dynamic_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    state = user_states.get(user_id, {}).get('chat_state', 0)
    
    asyncio.create_task(add_unique_reaction(update.message, chat_id))
    
    if state == 0:
        await send_animated_text(update, context, "تفضل\nكول يوت ثم اذكر اسم الاغنيه وراح توصلك")
        await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
        user_states[user_id] = {'chat_state': 1}
    else:
        await send_animated_text(update, context, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك")
        await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
        user_states[user_id] = {'chat_state': 0}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global channel_link, button_name
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = update.message.text.strip()
    is_group = update.message.chat.type in ['group', 'supergroup']
    
    if text == "تنظيف":
        asyncio.create_task(add_unique_reaction(update.message, chat_id))
        messages_to_clean = bot_audio_messages.get(chat_id, [])
        deleted_count = 0
        
        for msg_id in messages_to_clean:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                deleted_count += 1
            except:
                pass
                
        bot_audio_messages[chat_id] = []
        
        keyboard = [[InlineKeyboardButton("رب العالمين", url="tg://user?id=8597653867", style="destructive")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_animated_text(update, context, f"تم مسح {deleted_count} من الصوتيات\nلان امرتني مولاي", reply_markup=reply_markup)
        await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
        return

    if text == "ادت":
        if user_id == DEV_ID:
            asyncio.create_task(add_unique_reaction(update.message, chat_id))
            keyboard = [["تعيين الرابط", "تغيير اسم الزر"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await send_animated_text(
                update, context, 
                "تريد تغير اسم الزر دوس تغيير اسم الزر\nتريد تعين رابط الزر دوس تعيين الرابط", 
                reply_markup=reply_markup
            )
            await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
            return
        else:
            if is_group:
                return
            await send_dynamic_reply(update, context)
            return

    if user_id == DEV_ID and user_id in user_states and 'action' in user_states[user_id]:
        current_action = user_states[user_id].get('action')
        asyncio.create_task(add_unique_reaction(update.message, chat_id))
        
        if current_action == 'wait_link':
            is_url = re.match(r'^(https?://)?(t\.me|telegram\.me)/[a-zA-Z0-9_]+/?$', text)
            is_username = re.match(r'^@[a-zA-Z0-9_]+$', text)
            
            if is_url or is_username:
                channel_link = text if not is_username else f"https://t.me/{text[1:]}"
                await send_animated_text(update, context, "تم تعيين زر الاشتراك العلني تدلل\nءمهمواح")
                await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            else:
                await send_animated_text(update, context, "اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي")
                await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            return

        elif current_action == 'wait_name':
            words = text.split()
            if len(words) <= 3:
                button_name = text
                await send_animated_text(update, context, "غيرت الاسم بدون مشاكل يبعدي انه\nغير يدلل مولاي")
                await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            else:
                await send_animated_text(update, context, "الاسم اطول من المسموح به ثلاث كلمات\nك اقصى طول")
                await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
                user_states[user_id] = {'chat_state': 0}
            return

    if user_id == DEV_ID:
        if text == "تعيين الرابط":
            asyncio.create_task(add_unique_reaction(update.message, chat_id))
            user_states[user_id] = {'action': 'wait_link'}
            await update.message.reply_text(
                "ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", 
                reply_markup=ReplyKeyboardRemove(),
                reply_to_message_id=update.message.message_id
            )
            await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
            return
        elif text == "تغيير اسم الزر":
            asyncio.create_task(add_unique_reaction(update.message, chat_id))
            user_states[user_id] = {'action': 'wait_name'}
            await update.message.reply_text(
                "شتريد اسم الزر المرفق وي الرسايل\nيصير تاج راسي", 
                reply_markup=ReplyKeyboardRemove(),
                reply_to_message_id=update.message.message_id
            )
            await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
            return

    if is_group:
        if text == "بوت":
            await send_dynamic_reply(update, context)
        elif text.startswith("يوت "):
            asyncio.create_task(add_unique_reaction(update.message, chat_id))
            await process_youtube_search(update, context, text)
        return

    if text.startswith("يوت"):
        asyncio.create_task(add_unique_reaction(update.message, chat_id))
        await process_youtube_search(update, context, text)
        return

    await send_dynamic_reply(update, context)

async def process_youtube_search(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    global channel_link, button_name
    chat_id = update.message.chat_id
    
    match = re.match(r'^يوت\s+(.+)$', text)
    if not match:
        return

    search_query = match.group(1).strip()
    
    status_message = await send_animated_text(update, context, "يتم العثور على الاغنيه مولاي\nماتنتظر فدوا")
    emoji_message = await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)

    ydl_opts = {
        'format': 'bestaudio/best',
        'default_search': 'ytsearch1',
        'outtmpl': '%(title)s.ogg',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'vorbis',
        }],
        'quiet': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=True)
            video_info = info['entries'][0] if 'entries' in info else info
            audio_filename = ydl.prepare_filename(video_info)

        is_group = update.message.chat.type in ['group', 'supergroup']
        reply_markup = None
        
        if is_group and channel_link:
            keyboard = [[InlineKeyboardButton(button_name, url=channel_link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)

        audio_msg = await update.message.reply_voice(
            voice=open(audio_filename, 'rb'), 
            caption=video_info.get('title'), 
            reply_markup=reply_markup,
            reply_to_message_id=update.message.message_id
        )
        asyncio.create_task(add_unique_reaction(audio_msg, chat_id))
        
        if chat_id not in bot_audio_messages:
            bot_audio_messages[chat_id] = []
        bot_audio_messages[chat_id].append(audio_msg.message_id)
        
        await status_message.delete()
        await emoji_message.delete()
        os.remove(audio_filename)

    except Exception as e:
        print(f"Error: {e}")
        try:
            await status_message.delete()
            await emoji_message.delete()
        except:
            pass

        keyboard = [[InlineKeyboardButton("المطور", url="tg://user?id=8597653867", style="destructive")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_animated_text(update, context, "لم يتم العثور على طلبك اسفه الك\nيبعد كسي", reply_markup=reply_markup)
        await send_animated_text(update, context, "👉🏻🫦", is_emoji=True)
        
        if 'audio_filename' in locals() and os.path.exists(audio_filename):
            os.remove(audio_filename)

def main():
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN not found!")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(close_loop=False)

if __name__ == '__main__':
    main()
