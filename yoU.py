import os
import re
import asyncio
import itertools
import mimetypes
import aiosqlite
import aiofiles.os
import httpx
import yt_dlp

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "bot_database.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

REACTIONS = ["😭", "😡", "🌭", "🤣", "🥰", "🍓", "😘", "😁"]
DELAYS = [2.4, 4.2, 4.8, 3.6, 3.2, 2.3]

reaction_cycle = itertools.cycle(REACTIONS)
delay_cycle = itertools.cycle(DELAYS)

UPPER_CHARS = {'A', 'T', 'F', 'G', 'N', 'M', 'U', 'J', 'L', 'А', 'Б', 'И'}

TEXT_MESSAGES = [
    "اهلين وياك بوت ميديا تريد اشتغل \nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

msg_cycle = itertools.cycle(TEXT_MESSAGES)

BTN_PATTERNS = [
    [("سلوى", "tg://user?id=8800673233", "danger")],
    [("المطور", "tg://user?id=8859860635", "primary")],
    [("سلوى", "tg://user?id=8800673233", "danger")],
    [("مشاركه", "share", "primary")]
]

btn_cycle = itertools.cycle(BTN_PATTERNS)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS media_cache (
                url TEXT PRIMARY KEY,
                file_id TEXT,
                file_type TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS edit_messages (
                chat_id INTEGER PRIMARY KEY,
                user_msg_id INTEGER,
                bot_msg_id INTEGER
            )
        """)
        await db.commit()

async def get_setting(key: str, default: str = None) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def get_cached_media(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT file_id, file_type FROM media_cache WHERE url = ?", (url,)) as cursor:
            return await cursor.fetchone()

async def set_cached_media(url: str, file_id: str, file_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO media_cache (url, file_id, file_type) VALUES (?, ?, ?)", (url, file_id, file_type))
        await db.commit()

async def save_edit_msg(chat_id: int, user_msg_id: int, bot_msg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO edit_messages (chat_id, user_msg_id, bot_msg_id) VALUES (?, ?, ?)", (chat_id, user_msg_id, bot_msg_id))
        await db.commit()

async def get_and_del_edit_msg(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_msg_id, bot_msg_id FROM edit_messages WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        if row:
            await db.execute("DELETE FROM edit_messages WHERE chat_id = ?", (chat_id,))
            await db.commit()
        return row

def get_target_user_ids():
    user_ids = set()
    for pattern in BTN_PATTERNS:
        for btn_name, btn_val, _ in pattern:
            if btn_val.startswith("tg://user?id="):
                try:
                    user_ids.add(int(btn_val.split("id=")[1]))
                except ValueError:
                    pass
    return list(user_ids)

def transform_case(text: str) -> str:
    res = []
    for char in text:
        upper_char = char.upper()
        if upper_char in UPPER_CHARS:
            res.append(upper_char)
        else:
            res.append(char.lower())
    return "".join(res)

def clean_title(title: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9\s&\u0400-\u04FF]', '', title)
    return transform_case(cleaned)

def clean_uploader(uploader: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9\s_\u0400-\u04FF]', '', uploader)
    return transform_case(cleaned)

def filter_text_content(text: str) -> str:
    return transform_case(text)

async def apply_reaction(message: types.Message):
    delay = next(delay_cycle)
    reaction = next(reaction_cycle)
    await asyncio.sleep(delay)
    try:
        await message.react([types.ReactionTypeEmoji(emoji=reaction)])
    except Exception:
        pass

async def animate_text(sent_message: types.Message, full_text: str, reply_markup: InlineKeyboardMarkup = None):
    lines = full_text.split('\n')
    line_word_lists = [line.split() for line in lines]
    max_words = max((len(words) for words in line_word_lists), default=0)

    if max_words == 0:
        if reply_markup:
            try:
                await sent_message.edit_reply_markup(reply_markup=reply_markup)
            except Exception:
                pass
        return

    step = 0
    word_indices = []
    while step < max_words:
        word_indices.append(min(step + 2, max_words))
        step += 2
        if step >= max_words:
            break
        word_indices.append(min(step + 3, max_words))
        step += 3

    last_text = ""
    for idx in word_indices:
        current_lines = [" ".join(words[:idx]) for words in line_word_lists]
        current_text = "\n".join(current_lines)

        if current_text != last_text and current_text.strip():
            try:
                await sent_message.edit_text(current_text)
                last_text = current_text
            except Exception:
                pass
            await asyncio.sleep(0.3)

    if reply_markup or last_text != full_text:
        try:
            await sent_message.edit_text(full_text, reply_markup=reply_markup)
        except Exception:
            pass

def make_edit_markup(btn_style: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="تبديل اللغة", callback_data="lang_switch_menu", style=btn_style),
            InlineKeyboardButton(text="وضع اللغات", callback_data="toggle_lang_mode", style=btn_style)
        ],
        [
            InlineKeyboardButton(text="مسح", callback_data="delete_edit_msg")
        ]
    ])

@dp.message(F.text == "ادت")
async def handle_edit_command(message: types.Message):
    is_active = (await get_setting("lang_mode_active")) == "1"
    btn_style = "danger" if is_active else "primary"
    
    text_msg = (
        "تريد تفعل وضع اللغات دوس ع الزر الفوك يمين\n"
        "واذا تريد تبدل اللغة دوس الزر الفوك يسار"
    )
    
    markup = make_edit_markup(btn_style)
    sent_msg = await message.reply(text_msg, reply_markup=markup)
    await save_edit_msg(message.chat.id, message.message_id, sent_msg.message_id)

@dp.callback_query(F.data == "toggle_lang_mode")
async def callback_toggle_lang(callback: types.CallbackQuery):
    current_state = (await get_setting("lang_mode_active")) == "1"
    new_state = 0 if current_state else 1
    await set_setting("lang_mode_active", str(new_state))

    style = "danger" if new_state == 1 else "primary"
    markup = make_edit_markup(style)

    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        pass

    if new_state == 1:
        await callback.answer("تم تفعيل وضع اللغات مولاي\nالوضع ✔️", show_alert=True)
    else:
        await callback.answer("تم تعطيل وضع اللغات مولاي\nالوضع ❌", show_alert=True)

@dp.callback_query(F.data == "lang_switch_menu")
async def callback_lang_menu(callback: types.CallbackQuery):
    current_lang = (await get_setting("bot_target_lang")) or "rUS"
    text_msg = (
        "من هنا تكدر تغير لغة وضع اللغات تاج راسي\n"
        f"اللغة اللتي يعمل عليها البوت الان {current_lang}"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="rUS", callback_data="set_lang_rUS"),
            InlineKeyboardButton(text="eNG", callback_data="set_lang_eNG")
        ],
        [
            InlineKeyboardButton(text="عودة", callback_data="back_to_main_menu", style="success")
        ]
    ])

    try:
        await callback.message.edit_text(text_msg, reply_markup=markup)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("set_lang_"))
async def callback_set_lang(callback: types.CallbackQuery):
    lang = callback.data.split("_")[2]
    await set_setting("bot_target_lang", lang)
    
    text_msg = (
        "من هنا تكدر تغير لغة وضع اللغات تاج راسي\n"
        f"اللغة اللتي يعمل عليها البوت الان {lang}"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="rUS", callback_data="set_lang_rUS"),
            InlineKeyboardButton(text="eNG", callback_data="set_lang_eNG")
        ],
        [
            InlineKeyboardButton(text="عودة", callback_data="back_to_main_menu", style="success")
        ]
    ])

    try:
        await callback.message.edit_text(text_msg, reply_markup=markup)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "back_to_main_menu")
async def callback_back_menu(callback: types.CallbackQuery):
    is_active = (await get_setting("lang_mode_active")) == "1"
    style = "danger" if is_active else "primary"
    
    text_msg = (
        "تريد تفعل وضع اللغات دوس ع الزر الفوك يمين\n"
        "واذا تريد تبدل اللغة دوس الزر الفوك يسار"
    )
    
    markup = make_edit_markup(style)

    try:
        await callback.message.edit_text(text_msg, reply_markup=markup)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "delete_edit_msg")
async def callback_delete_msg(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    row = await get_and_del_edit_msg(chat_id)
    if row:
        user_msg_id, bot_msg_id = row
        try:
            await bot.delete_message(chat_id=chat_id, message_id=user_msg_id)
            await bot.delete_message(chat_id=chat_id, message_id=bot_msg_id)
        except Exception:
            pass
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

@dp.message(F.text.regexp(r'https?://\S+'))
async def handle_url(message: types.Message):
    asyncio.create_task(apply_reaction(message))
    
    url = message.text.strip()

    cached = await get_cached_media(url)
    if cached:
        cached_file_id, cached_type = cached
        if cached_type == 'video':
            sent_media = await message.reply_video(video=cached_file_id)
        elif cached_type == 'audio':
            sent_media = await message.reply_audio(audio=cached_file_id)
        else:
            sent_media = await message.reply_document(document=cached_file_id)

        asyncio.create_task(apply_reaction(sent_media))
        return

    status_text = "راح انفذ طلبك مولاي ودامص عيرك\nالعظيم بكل الوضعيات الزانية"
    first_line_init = status_text.split('\n')[0].split()[:2]
    status_msg = await message.reply(" ".join(first_line_init))
    asyncio.create_task(animate_text(status_msg, status_text))
    asyncio.create_task(apply_reaction(status_msg))
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': None,
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            filename = ydl.prepare_filename(info)

        uploader = info.get('uploader') or info.get('uploader_id') or ''
        title = info.get('title') or ''

        clean_up = clean_uploader(uploader)
        clean_ti = clean_title(title)

        if clean_up and clean_ti:
            final_name = f"{clean_up} - {clean_ti}"
        elif clean_ti:
            final_name = clean_ti
        else:
            final_name = clean_up

        mime_type, _ = mimetypes.guess_type(filename)
        ext = mimetypes.guess_extension(mime_type) or ".mp4"

        target_file = f"{final_name}{ext}"
        if await aiofiles.os.path.exists(filename) and filename != target_file:
            await aiofiles.os.rename(filename, target_file)
        else:
            target_file = filename

        media_file = types.FSInputFile(target_file)

        if mime_type and mime_type.startswith('video'):
            sent_media = await message.reply_video(video=media_file)
            file_id = sent_media.video.file_id
            m_type = 'video'
        elif mime_type and mime_type.startswith('audio'):
            sent_media = await message.reply_audio(audio=media_file)
            file_id = sent_media.audio.file_id
            m_type = 'audio'
        else:
            sent_media = await message.reply_document(document=media_file)
            file_id = sent_media.document.file_id
            m_type = 'document'

        await set_cached_media(url, file_id, m_type)

        asyncio.create_task(apply_reaction(sent_media))

        if await aiofiles.os.path.exists(target_file):
            await aiofiles.os.remove(target_file)

        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception:
        err_text = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
        asyncio.create_task(animate_text(status_msg, err_text))

@dp.message(~F.text.regexp(r'https?://\S+'))
async def handle_non_url_messages(message: types.Message):
    asyncio.create_task(apply_reaction(message))

    lang_mode = (await get_setting("lang_mode_active")) == "1"
    if lang_mode and message.text:
        txt = message.text
        has_arabic = bool(re.search(r'[\u0600-\u06FF]', txt))
        has_non_arabic = bool(re.search(r'[a-zA-Z0-9\u0400-\u04FF]', txt))

        if has_arabic and has_non_arabic:
            processed_txt = filter_text_content(txt)
            sent_msg = await message.reply(processed_txt if processed_txt else txt)
            asyncio.create_task(apply_reaction(sent_msg))
            return
        elif has_arabic and not has_non_arabic:
            target_lang = (await get_setting("bot_target_lang")) or "rUS"
            try:
                async with httpx.AsyncClient(timeout=5.0) as http_client:
                    resp = await http_client.get(
                        "https://translate.googleapis.com/translate_a/single",
                        params={
                            "client": "gtx",
                            "sl": "ar",
                            "tl": "ru" if target_lang == "rUS" else "en",
                            "dt": "t",
                            "q": txt
                        }
                    )
                    if resp.status_code == 200:
                        res_json = resp.json()
                        translated = "".join([item[0] for item in res_json[0] if item[0]])
                        txt = translated
            except Exception:
                pass
            
            processed_txt = filter_text_content(txt)
            sent_msg = await message.reply(processed_txt if processed_txt else txt)
            asyncio.create_task(apply_reaction(sent_msg))
            return

    text_to_send = next(msg_cycle)
    pattern = next(btn_cycle)

    bot_info = await bot.get_me()
    bot_username = bot_info.username

    inline_keyboard = []
    for btn_name, btn_val, btn_style in pattern:
        if btn_val == "share":
            share_url = f"https://t.me/share/url?url=@{bot_username}"
            inline_keyboard.append([InlineKeyboardButton(text=btn_name, url=share_url, style=btn_style)])
        else:
            inline_keyboard.append([InlineKeyboardButton(text=btn_name, url=btn_val, style=btn_style)])

    markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    
    first_words = " ".join(text_to_send.split('\n')[0].split()[:2])
    sent_msg = await message.reply(first_words)
    asyncio.create_task(animate_text(sent_msg, text_to_send, reply_markup=markup))
    asyncio.create_task(apply_reaction(sent_msg))

async def send_startup_messages():
    target_ids = get_target_user_ids()
    start_msg_text = "اشتغل البوت مرتلخ مولاي\nارضع عيرك ؟!"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="سلوى", url="tg://user?id=8800673233", style="danger")]
    ])

    for user_id in target_ids:
        try:
            await bot.send_message(chat_id=user_id, text=start_msg_text, reply_markup=markup)
        except Exception:
            pass

async def main():
    await init_db()
    await send_startup_messages()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
