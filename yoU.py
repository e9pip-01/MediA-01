import os
import re
import asyncio
import mimetypes
import shutil
import deep_translator
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.default import DefaultBotProperties
import yt_dlp
import orjson
import redis.asyncio as aioredis

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8859860635"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
MAX_FILE_SIZE = 456 * 1024 * 1024

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

download_semaphore = asyncio.Semaphore(3)
active_downloads = 0
waiting_count = 0

user_reply_counters = {}

UPPER_ENG = set("ATFGNMUJL")
UPPER_RUS = set("АБИ")

WELCOME_RESPONSES = [
    "اهلين وياك بوت ميديا تريد اشتغل \nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

MSG_SIZE_EXCEEDED = "عيرك طويل هواي دادي وكسي مايكدر\nيشيل هلكد عير طويل"
MSG_UNSUPPORTED_LINK = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"

def get_admin_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="ملكوت عيري", url=f"tg://user?id={ADMIN_ID}", style="primary"),
                InlineKeyboardButton(text="ملكوت عيري", url=f"tg://user?id={ADMIN_ID}", style="success"),
                InlineKeyboardButton(text="ملكوت عيري", url=f"tg://user?id={ADMIN_ID}", style="danger")
            ]
        ]
    )

def get_document_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="ملكوت كسي", url=f"tg://user?id={ADMIN_ID}", style="danger")
            ]
        ]
    )

async def get_user_settings(user_id: int):
    data = await redis_client.get(f"user_settings:{user_id}")
    if data:
        return orjson.loads(data)
    return {"lang_mode": False, "target_lang": "eNG"}

async def set_user_settings(user_id: int, settings: dict):
    await redis_client.set(f"user_settings:{user_id}", orjson.dumps(settings))

def is_english(char):
    return 'a' <= char.lower() <= 'z'

def is_russian(char):
    return ('а' <= char.lower() <= 'я') or char.lower() == 'ё'

def transform_publisher_name(name):
    res = []
    for char in name:
        if is_english(char):
            ch_upper = char.upper()
            res.append(ch_upper if ch_upper in UPPER_ENG else char.lower())
        elif is_russian(char):
            ch_upper = char.upper()
            res.append(ch_upper if ch_upper in UPPER_RUS else char.lower())
        else:
            res.append(char)
    return "".join(res)

def clean_publisher(name):
    if not name:
        return ""
    transformed = transform_publisher_name(name)
    cleaned = re.sub(r'[^a-zA-Z0-9\s_а-яА-ЯёЁ]', '', transformed)
    return cleaned.strip()

def clean_title(title):
    if not title:
        return "Media"
    cleaned = re.sub(r'[^a-zA-Z0-9\s\-&а-яА-ЯёЁ]', '', title)
    return cleaned.strip()

def transform_general_text(text):
    res = []
    for char in text:
        if is_english(char):
            ch_upper = char.upper()
            res.append(ch_upper if ch_upper in UPPER_ENG else char.lower())
        elif is_russian(char):
            ch_upper = char.upper()
            res.append(ch_upper if ch_upper in UPPER_RUS else char.lower())
        else:
            res.append(char)
    return "".join(res)

def is_pure_arabic(text):
    stripped = re.sub(r'[\s\d\W_]', '', text)
    if not stripped:
        return False
    return bool(re.fullmatch(r'[\u0600-\u06FF]+', stripped))

def is_url(text):
    url_pattern = re.compile(
        r'^(?:http|ftp)s?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    return bool(url_pattern.match(text.strip()))

def is_youtube_or_telegram(text):
    yt_tg_pattern = re.compile(
        r'(https?://)?(www\.)?(youtube\.com|youtu\.be|t\.me|telegram\.me)/.*', re.IGNORECASE
    )
    return bool(yt_tg_pattern.search(text.strip()))

async def get_settings_keyboard(user_id: int):
    settings = await get_user_settings(user_id)
    lang_active = settings["lang_mode"]
    curr_lang = settings["target_lang"]

    lang_btn_style = "success" if lang_active else "primary"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=curr_lang, callback_data="toggle_target_lang"),
                InlineKeyboardButton(text="وضع اللغات", callback_data="toggle_lang_mode", style=lang_btn_style)
            ],
            [
                InlineKeyboardButton(text="الغاء", callback_data="close_settings", style="primary")
            ]
        ]
    )

async def send_delayed_reply(message: Message, text: str):
    sent_msg = await message.reply(text)
    await asyncio.sleep(0.3)
    try:
        await sent_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
    except Exception:
        pass

@dp.message(F.text == "ادت")
async def handle_edit_cmd(message: Message):
    user_id = message.from_user.id
    kb = await get_settings_keyboard(user_id)
    text = "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    await message.reply(text, reply_markup=kb)

@dp.callback_query(F.data == "toggle_lang_mode")
async def process_toggle_lang_mode(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await get_user_settings(user_id)
    
    settings["lang_mode"] = not settings["lang_mode"]
    await set_user_settings(user_id, settings)

    kb = await get_settings_keyboard(user_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass

    if settings["lang_mode"]:
        alert_text = "تم تفعيل وضع اللغات\nالوضع ✅"
    else:
        alert_text = "تم تعطيل وضع اللغات\nالوضع ❌"

    await callback.answer(text=alert_text, show_alert=True)

@dp.callback_query(F.data == "toggle_target_lang")
async def process_toggle_target_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await get_user_settings(user_id)

    settings["target_lang"] = "rUS" if settings["target_lang"] == "eNG" else "eNG"
    await set_user_settings(user_id, settings)

    kb = await get_settings_keyboard(user_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "close_settings")
async def process_close_settings(callback: CallbackQuery):
    try:
        if callback.message.reply_to_message:
            await callback.message.reply_to_message.delete()
    except Exception:
        pass

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

async def process_download_task(message: Message, url: str):
    global active_downloads, waiting_count
    
    status_msg = await message.reply("دانفذ طلبك انتظر مولاي ماراح اضل هواي\nامص عيرك ءعهقءعهقءعهق امم؟!  0%")
    await asyncio.sleep(0.3)
    try:
        await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
    except Exception:
        pass

    user_dir = f"downloads/{message.from_user.id}_{message.message_id}"
    os.makedirs(user_dir, exist_ok=True)

    try:
        ydl_info_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_info_opts).extract_info(url, download=False))
        except Exception:
            await status_msg.edit_text(MSG_UNSUPPORTED_LINK)
            await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
            shutil.rmtree(user_dir, ignore_errors=True)
            return

        if not info:
            await status_msg.edit_text(MSG_UNSUPPORTED_LINK)
            await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
            shutil.rmtree(user_dir, ignore_errors=True)
            return

        file_size = info.get('filesize') or info.get('filesize_approx') or 0
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(MSG_SIZE_EXCEEDED)
            await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
            shutil.rmtree(user_dir, ignore_errors=True)
            return

        publisher_raw = info.get('uploader') or info.get('channel') or ""
        publisher_clean = clean_publisher(publisher_raw)
        title_clean = clean_title(info.get('title', ''))

        if publisher_clean:
            final_base_name = f"{publisher_clean} - {title_clean}"
        else:
            final_base_name = title_clean

        outtmpl_str = os.path.join(user_dir, f"{final_base_name}.%(ext)s")

        last_percent = [-15]

        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    pct = int((downloaded / total) * 100)
                    if pct >= last_percent[0] + 15:
                        last_percent[0] = (pct // 15) * 15
                        asyncio.run_coroutine_threadsafe(
                            update_progress_ui(status_msg, last_percent[0]),
                            loop
                        )

        ydl_opts = {
            'outtmpl': outtmpl_str,
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo+bestaudio/best',
        }

        try:
            await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))
        except Exception:
            await status_msg.edit_text(MSG_UNSUPPORTED_LINK)
            await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
            shutil.rmtree(user_dir, ignore_errors=True)
            return

        downloaded_files = [os.path.join(user_dir, f) for f in os.listdir(user_dir)]
        if not downloaded_files:
            await status_msg.edit_text(MSG_UNSUPPORTED_LINK)
            await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
            shutil.rmtree(user_dir, ignore_errors=True)
            return

        file_path = downloaded_files[0]
        actual_size = os.path.getsize(file_path)

        if actual_size > MAX_FILE_SIZE:
            await status_msg.edit_text(MSG_SIZE_EXCEEDED)
            await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
            shutil.rmtree(user_dir, ignore_errors=True)
            return

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        file_name = os.path.basename(file_path)

        await status_msg.edit_text("✅")
        await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())

        from aiogram.types import FSInputFile
        input_file = FSInputFile(path=file_path, filename=file_name)

        await message.reply_document(
            document=input_file,
            reply_markup=get_document_keyboard()
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception:
        try:
            await status_msg.edit_text(MSG_UNSUPPORTED_LINK)
            await status_msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
        except Exception:
            pass
    finally:
        shutil.rmtree(user_dir, ignore_errors=True)

async def update_progress_ui(msg: Message, pct: int):
    try:
        await msg.edit_text(f"دانفذ طلبك انتظر مولاي ماراح اضل هواي\nامص عيرك ءعهقءعهقءعهق امم؟!  {pct}%")
        await msg.edit_reply_markup(reply_markup=get_admin_inline_keyboard())
    except Exception:
        pass

@dp.message(F.text)
async def handle_all_messages(message: Message):
    global active_downloads, waiting_count

    user_id = message.from_user.id
    text = message.text.strip()

    if text == "ادت":
        return

    is_link = is_url(text)
    is_yt_tg = is_youtube_or_telegram(text)

    if is_link and not is_yt_tg:
        if active_downloads + waiting_count >= 6:
            return

        if active_downloads >= 3:
            waiting_count += 1
            async with download_semaphore:
                waiting_count -= 1
                active_downloads += 1
                try:
                    await process_download_task(message, text)
                finally:
                    active_downloads -= 1
        else:
            async with download_semaphore:
                active_downloads += 1
                try:
                    await process_download_task(message, text)
                finally:
                    active_downloads -= 1
        return

    settings = await get_user_settings(user_id)

    if settings["lang_mode"] and is_pure_arabic(text):
        target_code = "en" if settings["target_lang"] == "eNG" else "ru"
        try:
            translated = deep_translator.GoogleTranslator(source='auto', target=target_code).translate(text)
            await send_delayed_reply(message, translated)
        except Exception:
            await send_delayed_reply(message, text)
        return

    if not is_link:
        has_eng = any(is_english(c) for c in text)
        has_rus = any(is_russian(c) for c in text)

        if has_eng or has_rus:
            transformed = transform_general_text(text)
            await send_delayed_reply(message, transformed)
            return

    idx = user_reply_counters.get(user_id, 0)
    response_text = WELCOME_RESPONSES[idx]
    user_reply_counters[user_id] = (idx + 1) % len(WELCOME_RESPONSES)

    await send_delayed_reply(message, response_text)

async def on_startup(bot: Bot):
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text="اشتغل البوت مرتلخ مولاي\nارضع عيرك ؟!",
            reply_markup=get_admin_inline_keyboard()
        )
    except Exception:
        pass

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
