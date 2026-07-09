import asyncio
from aiogram import types, Bot
from aiogram.enums import ChatType

import STriNGs
import dATAbAse

async def animate_text_7_3(message: types.Message, text: str, bot: Bot = None, reply_markup=None, keyboard_markup=None):
    if not text:
        return None

    pattern = [7, 3]
    pattern_idx = 0

    total_len = len(text)
    current_len = min(pattern[pattern_idx], total_len)
    pattern_idx = (pattern_idx + 1) % 2

    initial_text = text[:current_len]

    if keyboard_markup:
        sent_msg = await message.reply(initial_text, reply_markup=keyboard_markup)
    else:
        sent_msg = await message.reply(initial_text)

    await asyncio.sleep(0.3)

    while current_len < total_len:
        step = pattern[pattern_idx]
        pattern_idx = (pattern_idx + 1) % 2

        current_len = min(current_len + step, total_len)
        current_text = text[:current_len]

        try:
            await sent_msg.edit_text(current_text)
            await asyncio.sleep(0.3)
        except Exception:
            pass

    try:
        await sent_msg.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass

    return sent_msg

async def handle_group_service_messages(message: types.Message):
    status = await dATAbAse.get_notification_status(message.chat.id)
    if status == 1:
        try:
            await message.delete()
        except Exception:
            pass

async def handle_group_logic(message: types.Message, animate_func) -> bool:
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        return False

    text = message.text.strip() if message.text else ""
    user_id = message.from_user.id if message.from_user else message.chat.id
    chat_id = message.chat.id

    if text.lower() == "ادت":
        if await STriNGs.is_user_allowed_for_edit(message):
            invoker_id = message.from_user.id if message.from_user else message.chat.id
            await animate_text_7_3(message, STriNGs.PANEL_TITLE_MSG, keyboard_markup=None)
            return True

    if text == STriNGs.BTN_MUTE:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_notification_status(chat_id, 1)
            await animate_text_7_3(message, STriNGs.MUTE_SUCCESS_MSG)
            return True

    if text == STriNGs.BTN_UNMUTE:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_notification_status(chat_id, 0)
            await animate_text_7_3(message, STriNGs.UNMUTE_SUCCESS_MSG)
            return True

    if text == "بوت":
        current_index = await dATAbAse.get_user_step(user_id)
        handler_func = STriNGs.RESPONSE_HANDLERS[current_index]
        next_index = (current_index + 1) % len(STriNGs.RESPONSE_HANDLERS)
        await dATAbAse.update_user_step(user_id, next_index)
        await handler_func(message, animate_text_7_3)
        return True

    return False
