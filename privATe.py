import re
from aiogram import types, Bot
from aiogram.enums import ChatType

import STriNGs
import dATAbAse
from order import handle_start_whisper_session, process_whisper_input

def validate_custom_username(text: str) -> bool:
    clean = text.replace("@", "").strip()
    if not clean:
        return False
    if clean[0].isdigit() or clean[0] == '-' or clean[-1] == '-':
        return False
    if not re.match(r'^[a-zA-Z0-9_\-]+$', clean):
        return False
    return True

def process_custom_languages(text: str) -> str:
    ENGLISH_UPPER_TARGETS = ['a', 'f', 't', 'u', 'g', 'n', 'm', 'j']
    RUSSIAN_UPPER_TARGETS = ['а', 'и', 'б']

    ENGLISH_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    RUSSIAN_ALPHABET = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'

    result = []
    for char in text:
        if char.isalpha():
            if char in ENGLISH_ALPHABET:
                if char.lower() in ENGLISH_UPPER_TARGETS:
                    result.append(char.upper())
                else:
                    result.append(char.lower())
            elif char in RUSSIAN_ALPHABET:
                if char.lower() in RUSSIAN_UPPER_TARGETS:
                    result.append(char.upper())
                else:
                    result.append(char.lower())
            else:
                result.append(char)
        else:
            result.append(char)
    return "".join(result)

async def check_force_subscription(bot: Bot, user_id: int) -> bool:
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

async def handle_private_logic(message: types.Message, bot: Bot, animate_func, trigger_reaction_func, safe_food_func) -> bool:
    if message.chat.type != ChatType.PRIVATE:
        return False

    text = message.text.strip() if message.text else ""
    user_id = message.from_user.id

    if text.startswith("/start whsp_"):
        payload = text.split("/start ")[1]
        await handle_start_whisper_session(message, payload, bot, trigger_reaction_func, safe_food_func)
        return True

    whisper_processed = await process_whisper_input(message, bot, trigger_reaction_func, safe_food_func)
    if whisper_processed:
        return True

    current_admin_state = await dATAbAse.get_admin_state(user_id)
    if current_admin_state == "wait_link" and await STriNGs.is_user_allowed_for_edit(message):
        is_link_input = text.startswith("http://") or text.startswith("https://") or "t.me/" in text
        is_user_input = text.startswith("@") or validate_custom_username(text)
        
        if is_link_input or is_user_input:
            await dATAbAse.set_force_sub_link(text)
            await dATAbAse.set_admin_state(user_id, "none")
            await animate_func(message, STriNGs.SET_LINK_SUCCESS_MSG, keyboard_markup=types.ReplyKeyboardRemove())
        else:
            await dATAbAse.set_admin_state(user_id, "none")
            await animate_func(message, STriNGs.INVALID_LINK_MSG, keyboard_markup=types.ReplyKeyboardRemove())
        return True

    if text == "ادت البوت":
        if user_id in STriNGs.ALLOWED_DEVELOPERS:
            await animate_func(message, STriNGs.BOT_EDIT_PANEL_MSG, keyboard_markup=STriNGs.get_bot_edit_keyboard())
            return True

    if text == STriNGs.BTN_SET_LINK:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_admin_state(user_id, "wait_link")
            await animate_func(message, STriNGs.ASK_LINK_MSG)
            return True

    if text == STriNGs.BTN_SHOW_MSG:
        if await STriNGs.is_user_allowed_for_edit(message):
            current_link = await dATAbAse.get_force_sub_link()
            inline_kb = await STriNGs.get_force_sub_inline(current_link)
            await animate_func(message, STriNGs.FORCE_SUB_TEXT, reply_markup=inline_kb)
            return True

    if not await check_force_subscription(bot, user_id):
        current_link = await dATAbAse.get_force_sub_link()
        inline_kb = await STriNGs.get_force_sub_inline(current_link)
        await animate_func(message, STriNGs.FORCE_SUB_TEXT, reply_markup=inline_kb)
        return True

    if text == "الغاء":
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_admin_state(user_id, "none")
            await animate_func(message, STriNGs.CANCEL_SUCCESS_MSG, keyboard_markup=types.ReplyKeyboardRemove())
            return True

    has_english = bool(re.search(r'[a-zA-Z]', text))
    has_russian = bool(re.search(r'[а-яА-Я]', text))
    
    if (has_english or has_russian) and not (validate_custom_username(text) and not text.startswith("@")):
        processed_text = process_custom_languages(text)
        await animate_func(message, processed_text)
        return True

    return False
