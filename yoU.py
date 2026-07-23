import os
import re
import sys
import math
import random
import asyncio
import mimetypes
from typing import Dict, List, Set, Optional

from googletrans import Translator
import yt_dlp

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    BufferedInputFile
)
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEV_ID = 8800673233

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
translator = Translator()

lang_mode_users: Set[int] = set()
user_target_lang: Dict[int, str] = {}
user_edit_msg_ids: Dict[int, List[int]] = {}

user_queues: Dict[int, asyncio.Queue] = {}
user_active_count: Dict[int, int] = {}

enabled_chats: Set[int] = set()

EMOJIS_LIST = ["🥪", "🍣", "🍔", "🥞", "🌭"]
REACTION_EMOJIS = ["😘", "😭", "🍓", "🤣", "🥰"]
REACTION_TIMERS = [2.4, 4.2, 3.2, 2.3, 3.6]

recent_reactions: List[str] = []
recent_timers: List[float] = []

dev_buttons_toggle: Dict[int, bool] = {}
msg_counter: Dict[int, int] = {}

UPPER_ENG = set("ATFGNMUJL")
UPPER_RUS = set("АИБ")

ORDERED_REPLIES = [
    "اهلين وياك بوت ميديا تريد اشتغل \nدز رابط وتدلل",
    "مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
    "راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

def get_next_ordered_reply(user_id: int) -> str:
    current_index = msg_counter.get(user_id, 0)
    selected_text = ORDERED_REPLIES[current_index]
    msg_counter[user_id] = (current_index + 1) % len(ORDERED_REPLIES)
    return selected_text

def transform_english(text: str) -> str:
    res = []
    for char in text:
        if char.isalpha() and ('a' <= char.lower() <= 'z'):
            c_up = char.upper()
            if c_up in UPPER_ENG:
                res.append(c_up)
            else:
                res.append(char.lower())
        else:
            res.append(char)
    return "".join(res)

def transform_russian(text: str) -> str:
    res = []
    for char in text:
        c_up = char.upper()
        if c_up in UPPER_RUS:
            res.append(c_up)
        else:
            res.append(char.lower())
    return "".join(res)

def filter_title(text: str) -> str:
    allowed = set("-& ")
    return "".join(c for c in text if c.isalnum() or c in allowed)

def filter_uploader(text: str) -> str:
    allowed = set("_ ")
    return "".join(c for c in text if c.isalnum() or c in allowed)

def has_arabic(text: str) -> bool:
    return bool(re.search(r'[\u0600-\u06FF]', text))

def has_english(text: str) -> bool:
    return bool(re.search(r'[a-zA-Z]', text))

def has_russian(text: str) -> bool:
    return bool(re.search(r'[\u0400-\u04FF]', text))

def is_url(text: str) -> bool:
    if "telegram.org" in text or "t.me" in text:
        return False
    if "youtube.com" in text or "youtu.be" in text:
        return False
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    return bool(url_pattern.search(text))

async def handle_reaction(message: Message, chat_type: ChatType, is_owner: bool, is_bot_msg: bool):
    if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        if not (is_owner or is_bot_msg):
            return

    global recent_reactions, recent_timers

    avail_emojis = [e for e in REACTION_EMOJIS if e not in recent_reactions[-4:]]
    if not avail_emojis:
        avail_emojis = REACTION_EMOJIS
    chosen_emoji = random.choice(avail_emojis)
    recent_reactions.append(chosen_emoji)
    if len(recent_reactions) > 10:
        recent_reactions.pop(0)

    avail_timers = [t for t in REACTION_TIMERS if t not in recent_timers[-3:]]
    if not avail_timers:
        avail_timers = REACTION_TIMERS
    chosen_timer = random.choice(avail_timers)
    recent_timers.append(chosen_timer)
    if len(recent_timers) > 10:
        recent_timers.pop(0)

    await asyncio.sleep(chosen_timer)
    try:
        await bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[{"type": "emoji", "emoji": chosen_emoji}]
        )
    except Exception:
        pass

async def send_typing_animated(chat_id: int, text: str, reply_to_id: int) -> Message:
    lines = text.split('\n')
    words_per_line = [line.split() for line in lines]
    max_words = max(len(w) for w in words_per_line) if words_per_line else 0

    steps = []
    pattern = [2, 3, 4]
    pat_idx = 0
    curr_w = 0

    while curr_w < max_words:
        step_inc = pattern[pat_idx % len(pattern)]
        curr_w += step_inc
        pat_idx += 1
        
        step_lines = []
        for line_words in words_per_line:
            taken = line_words[:min(curr_w, len(line_words))]
            step_lines.append(" ".join(taken))
        steps.append("\n".join(step_lines))

    if not steps:
        steps = [text]

    sent_msg = await bot.send_message(
        chat_id=chat_id,
        text=steps[0],
        reply_to_message_id=reply_to_id if reply_to_id > 0 else None
    )

    emoji_sent = False
    for i in range(1, len(steps)):
        await asyncio.sleep(0.3)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=sent_msg.message_id,
                text=steps[i]
            )
        except Exception:
            pass
        
        if i == 1 and not emoji_sent:
            emoji_sent = True
            chosen_e = random.choice(EMOJIS_LIST)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chosen_e,
                    reply_to_message_id=sent_msg.message_id
                )
            except Exception:
                pass

    if len(steps) <= 1 and not emoji_sent:
        chosen_e = random.choice(EMOJIS_LIST)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chosen_e,
                reply_to_message_id=sent_msg.message_id
            )
        except Exception:
            pass

    return sent_msg

async def edit_typing_animated(chat_id: int, message_id: int, text: str):
    lines = text.split('\n')
    words_per_line = [line.split() for line in lines]
    max_words = max(len(w) for w in words_per_line) if words_per_line else 0

    steps = []
    pattern = [2, 3, 4]
    pat_idx = 0
    curr_w = 0

    while curr_w < max_words:
        step_inc = pattern[pat_idx % len(pattern)]
        curr_w += step_inc
        pat_idx += 1
        
        step_lines = []
        for line_words in words_per_line:
            taken = line_words[:min(curr_w, len(line_words))]
            step_lines.append(" ".join(taken))
        steps.append("\n".join(step_lines))

    if not steps:
        steps = [text]

    for i in range(len(steps)):
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=steps[i]
            )
        except Exception:
            pass
        if i < len(steps) - 1:
            await asyncio.sleep(0.3)

def build_edit_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    color_style = "danger" if is_active else "primary"
    btn_lang_mode = InlineKeyboardButton(text="وضع اللغات", callback_data="toggle_lang_mode", style=color_style)
    btn_switch_lang = InlineKeyboardButton(text="تبديل اللغة", callback_data="open_switch_lang", style=color_style)
    btn_clear = InlineKeyboardButton(text="مسح", callback_data="clear_edit_menu", style="danger")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn_switch_lang, btn_lang_mode],
        [btn_clear]
    ])
    return kb

@dp.message(Command("start"))
async def start_handler(message: Message):
    asyncio.create_task(handle_reaction(message, message.chat.type, False, False))

@dp.message(Command("تفعيل"))
async def enable_group(message: Message):
    if message.chat.type in [ChatType.PRIVATE]:
        return
    
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status != ChatMemberStatus.CREATOR:
        return

    enabled_chats.add(message.chat.id)
    text = "¹# - تم تفعيل البوت مولاي\nارسل رابط الان"
    sent = await send_typing_animated(message.chat.id, text, message.message_id)
    asyncio.create_task(handle_reaction(sent, message.chat.type, True, True))

@dp.message(Command("تعطيل"))
async def disable_group(message: Message):
    if message.chat.type in [ChatType.PRIVATE]:
        return

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status != ChatMemberStatus.CREATOR:
        return

    enabled_chats.discard(message.chat.id)
    text = "¹# - تم تعطيل اليوت مولاي\nارسل رابط الان"
    sent = await send_typing_animated(message.chat.id, text, message.message_id)
    asyncio.create_task(handle_reaction(sent, message.chat.type, True, True))

@dp.message(F.text == "ادت")
async def edit_command_handler(message: Message):
    asyncio.create_task(handle_reaction(message, message.chat.type, False, False))
    
    user_id = message.from_user.id
    is_active = user_id in lang_mode_users
    
    text = "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    sent_msg = await send_typing_animated(message.chat.id, text, message.message_id)
    
    kb = build_edit_keyboard(is_active)
    await bot.edit_message_reply_markup(
        chat_id=message.chat.id,
        message_id=sent_msg.message_id,
        reply_markup=kb
    )
    
    if user_id not in user_edit_msg_ids:
        user_edit_msg_ids[user_id] = []
    
    user_edit_msg_ids[user_id].append(sent_msg.message_id)
    
    if len(user_edit_msg_ids[user_id]) > 3:
        oldest_msg_id = user_edit_msg_ids[user_id].pop(0)
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=oldest_msg_id)
        except Exception:
            pass

@dp.callback_query(F.data == "toggle_lang_mode")
async def cb_toggle_lang_mode(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in lang_mode_users:
        lang_mode_users.remove(user_id)
        is_active = False
        alert_text = "تم تعطيل وضع اللغات\nالوضع ❌"
    else:
        lang_mode_users.add(user_id)
        is_active = True
        alert_text = "تم تفعيل وضع اللغات\nالوضع ✅"
        
    await callback.answer(alert_text, show_alert=True)
    kb = build_edit_keyboard(is_active)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass

@dp.callback_query(F.data == "open_switch_lang")
async def cb_open_switch_lang(callback: CallbackQuery):
    text = "تريد تغير لغة وضع اللغات منا\nاكو زرين عندك"
    btn_eng = InlineKeyboardButton(text="eNG", callback_data="set_lang_eNG", style="primary")
    btn_rus = InlineKeyboardButton(text="rUS", callback_data="set_lang_rUS", style="primary")
    btn_back = InlineKeyboardButton(text="عودة", callback_data="back_to_edit", style="secondary")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn_rus, btn_eng],
        [btn_back]
    ])
    try:
        await callback.message.edit_text(text=text, reply_markup=kb)
    except Exception:
        pass

@dp.callback_query(F.data.in_({"set_lang_eNG", "set_lang_rUS"}))
async def cb_set_language(callback: CallbackQuery):
    user_id = callback.from_user.id
    chosen = "eNG" if callback.data == "set_lang_eNG" else "rUS"
    user_target_lang[user_id] = chosen
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    text = f"تم تغيير لغة وضع اللغات مولاي\nصارت {chosen}"
    await edit_typing_animated(callback.message.chat.id, callback.message.message_id, text)
    
    is_active = user_id in lang_mode_users
    edit_text = "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    kb = build_edit_keyboard(is_active)
    try:
        await callback.message.edit_text(text=edit_text, reply_markup=kb)
    except Exception:
        pass

@dp.callback_query(F.data == "back_to_edit")
async def cb_back_to_edit(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_active = user_id in lang_mode_users
    text = "تريد تغير لغة وضع اللغات دوس ع الزر الفوك يسار\nتريد تفعل وضع اللغات دوس ع الزر الفوك يمين"
    kb = build_edit_keyboard(is_active)
    try:
        await callback.message.edit_text(text=text, reply_markup=kb)
    except Exception:
        pass

@dp.callback_query(F.data == "clear_edit_menu")
async def cb_clear_edit_menu(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id
    reply_to = callback.message.reply_to_message
    
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass
        
    if reply_to:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=reply_to.message_id)
        except Exception:
            pass

async def process_download_job(message: Message, url: str):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    status_msg = await send_typing_animated(
        chat_id,
        "دانفذ طلبك انتظر مولاي ماراح اضل هواي\nراح امص عيرك ءعهقءعهقءعهق",
        message.message_id
    )

    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
        
        if not info:
            raise Exception("No info extracted")

        entries = info.get('entries', [info])
        batches = [entries[i:i + 8] for i in range(0, len(entries), 8)]

        target_lang = user_target_lang.get(user_id, "eNG")

        for batch in batches:
            for item in batch:
                direct_url = item.get('url')
                uploader = item.get('uploader') or item.get('channel') or "Publisher"
                title = item.get('title') or "Media"
                ext = item.get('ext') or "bin"

                if has_arabic(uploader):
                    dest = 'en' if target_lang == "eNG" else 'ru'
                    uploader = translator.translate(uploader, dest=dest).text
                
                if has_arabic(title):
                    dest = 'en' if target_lang == "eNG" else 'ru'
                    title = translator.translate(title, dest=dest).text

                if has_russian(uploader):
                    uploader = transform_russian(uploader)
                elif has_english(uploader):
                    uploader = transform_english(uploader)

                if has_russian(title):
                    title = transform_russian(title)
                elif has_english(title):
                    title = transform_english(title)

                uploader = filter_uploader(uploader)
                title = filter_title(title)

                rand_num = random.randint(100, 999)
                filename = f"{uploader} - {title}_{rand_num}.{ext}"

                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(direct_url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            content_type = resp.headers.get('Content-Type', '')
                            mime_ext = mimetypes.guess_extension(content_type.split(';')[0])
                            if mime_ext:
                                filename = f"{uploader} - {title}_{rand_num}{mime_ext}"
                            
                            document = BufferedInputFile(data, filename=filename)
                            await bot.send_document(
                                chat_id=chat_id,
                                document=document,
                                reply_to_message_id=message.message_id
                            )

        success_msg = "نيكني استاهل تشكني اطيعك مثل\nعديمة الكرامة"
        await send_typing_animated(chat_id, success_msg, message.message_id)

    except Exception:
        fail_msg = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=fail_msg
            )
        except Exception:
            await send_typing_animated(chat_id, fail_msg, message.message_id)

async def queue_worker(user_id: int):
    while True:
        job_coro = await user_queues[user_id].get()
        user_active_count[user_id] = user_active_count.get(user_id, 0) + 1
        try:
            await job_coro
        finally:
            user_active_count[user_id] -= 1
            user_queues[user_id].task_done()

@dp.message()
async def general_message_handler(message: Message):
    chat_type = message.chat.type
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""

    is_owner = False
    if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        if chat_id not in enabled_chats:
            return
        
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == ChatMemberStatus.CREATOR:
            is_owner = True
            
        if text != "بوت" and member.status not in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]:
            return

    asyncio.create_task(handle_reaction(message, chat_type, is_owner, False))

    if text == "بوت" and chat_type != ChatType.PRIVATE:
        chosen_text = get_next_ordered_reply(user_id)
        sent = await send_typing_animated(chat_id, chosen_text, message.message_id)
        asyncio.create_task(handle_reaction(sent, chat_type, is_owner, True))
        return

    if is_url(text):
        if user_id not in user_queues:
            user_queues[user_id] = asyncio.Queue()
            asyncio.create_task(queue_worker(user_id))

        if user_queues[user_id].qsize() >= 4:
            return

        await user_queues[user_id].put(process_download_job(message, text))
        return

    if user_id in lang_mode_users and chat_type == ChatType.PRIVATE:
        target_lang = user_target_lang.get(user_id, "eNG")
        has_ar = has_arabic(text)
        has_eng = has_english(text)
        has_rus = has_russian(text)

        if has_ar and not has_eng and not has_rus:
            dest = 'en' if target_lang == "eNG" else 'ru'
            translated = translator.translate(text, dest=dest).text
            if target_lang == "eNG":
                res = transform_english(translated)
            else:
                res = transform_russian(translated)
            sent = await send_typing_animated(chat_id, res, message.message_id)
            asyncio.create_task(handle_reaction(sent, chat_type, False, True))
            return

        if (has_eng or has_rus) and has_ar:
            res = text
            if has_eng:
                res = transform_english(res)
            if has_rus:
                res = transform_russian(res)
            sent = await send_typing_animated(chat_id, res, message.message_id)
            asyncio.create_task(handle_reaction(sent, chat_type, False, True))
            return

        if not has_ar and (has_eng or has_rus):
            res = text
            if has_eng:
                res = transform_english(res)
            if has_rus:
                res = transform_russian(res)
            sent = await send_typing_animated(chat_id, res, message.message_id)
            asyncio.create_task(handle_reaction(sent, chat_type, False, True))
            return

        dest = 'en' if target_lang == "eNG" else 'ru'
        translated = translator.translate(text, dest=dest).text
        if target_lang == "eNG":
            res = transform_english(translated)
        else:
            res = transform_russian(translated)
        sent = await send_typing_animated(chat_id, res, message.message_id)
        asyncio.create_task(handle_reaction(sent, chat_type, False, True))
        return

    if chat_type == ChatType.PRIVATE:
        chosen_text = get_next_ordered_reply(user_id)
        sent = await send_typing_animated(chat_id, chosen_text, message.message_id)

        toggle = dev_buttons_toggle.get(user_id, False)
        if not toggle:
            btn = InlineKeyboardButton(
                text="المطور",
                url="tg://user?id=8800673233",
                style="danger"
            )
        else:
            btn = InlineKeyboardButton(
                text="تواصل مع المطور",
                url="tg://user?id=8800673233",
                style="primary"
            )
        dev_buttons_toggle[user_id] = not toggle

        kb = InlineKeyboardMarkup(inline_keyboard=[[btn]])
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=sent.message_id,
                reply_markup=kb
            )
        except Exception:
            pass

        asyncio.create_task(handle_reaction(sent, chat_type, False, True))

async def main():
    startup_text = "اشتغل البوت مرتلخ مولاي\nارضع عيرك ؟!"
    btn_god = InlineKeyboardButton(text="رب العالمين", callback_data="god_btn", style="primary")
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_god]])

    try:
        sent = await send_typing_animated(DEV_ID, startup_text, 0)
        await bot.edit_message_reply_markup(
            chat_id=DEV_ID,
            message_id=sent.message_id,
            reply_markup=kb
        )
        asyncio.create_task(handle_reaction(sent, ChatType.PRIVATE, True, True))
    except Exception:
        pass

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
