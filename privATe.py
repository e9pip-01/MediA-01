import re
from aiogram import types, Bot
from aiogram.enums import ChatType

import strings
import database

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
    link = await database.get_force_sub_link()
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

    current_admin_state = await database.get_admin_state(user_id)
    if current_admin_state == "wait_link" and await strings.is_user_allowed_for_edit(message):
        is_link_input = text.startswith("http://") or text.startswith("https://") or "t.me/" in text
        is_user_input = text.startswith("@") or validate_custom_username(text)
        
        if is_link_input or is_user_input:
            await database.set_force_sub_link(text)
            await database.set_admin_state(user_id, "none")
            await animate_func(message, strings.SET_LINK_SUCCESS_MSG, keyboard_markup=types.ReplyKeyboardRemove())
        else:
            await database.set_admin_state(user_id, "none")
            await animate_func(message, strings.INVALID_LINK_MSG, keyboard_markup=types.ReplyKeyboardRemove())
        return True

    if text == "ادت البوت":
        if user_id in strings.ALLOWED_DEVELOPERS:
            await animate_func(message, strings.BOT_EDIT_PANEL_MSG, keyboard_markup=strings.get_bot_edit_keyboard())
            return True

    if text == strings.BTN_SET_LINK:
        if await strings.is_user_allowed_for_edit(message):
            await database.set_admin_state(user_id, "wait_link")
            await animate_func(message, strings.ASK_LINK_MSG)
            return True

    if text == strings.BTN_SHOW_MSG:
        if await strings.is_user_allowed_for_edit(message):
            current_link = await database.get_force_sub_link()
            inline_kb = await strings.get_force_sub_inline(current_link)
            await animate_func(message, strings.FORCE_SUB_TEXT, reply_markup=inline_kb)
            return True

    if not await check_force_subscription(bot, user_id):
        current_link = await database.get_force_sub_link()
        inline_kb = await strings.get_force_sub_inline(current_link)
        await animate_func(message, strings.FORCE_SUB_TEXT, reply_markup=inline_kb)
        return True

    if text == "الغاء":
        if await strings.is_user_allowed_for_edit(message):
            await database.set_admin_state(user_id, "none")
            await animate_func(message, strings.CANCEL_SUCCESS_MSG, keyboard_markup=types.ReplyKeyboardRemove())
            return True

    has_english = bool(re.search(r'[a-zA-Z]', text))
    has_russian = bool(re.search(r'[а-яА-Я]', text))
    
    if (has_english or has_russian) and not (validate_custom_username(text) and not text.startswith("@")):
        processed_text = process_custom_languages(text)
        await animate_func(message, processed_text)
        return True

    return False
