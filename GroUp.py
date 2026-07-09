from aiogram import types, Bot
from aiogram.enums import ChatType

import STriNGs
import dATAbAse

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
            await animate_func(message, STriNGs.PANEL_TITLE_MSG, reply_markup=STriNGs.get_keyboard_markup(invoker_id))
            return True

    if text == STriNGs.BTN_MUTE:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_notification_status(chat_id, 1)
            await animate_func(message, STriNGs.MUTE_SUCCESS_MSG)
            return True

    if text == STriNGs.BTN_UNMUTE:
        if await STriNGs.is_user_allowed_for_edit(message):
            await dATAbAse.set_notification_status(chat_id, 0)
            await animate_func(message, STriNGs.UNMUTE_SUCCESS_MSG)
            return True

    if text == "بوت":
        current_index = await dATAbAse.get_user_step(user_id)
        handler_func = STriNGs.RESPONSE_HANDLERS[current_index]
        next_index = (current_index + 1) % len(STriNGs.RESPONSE_HANDLERS)
        await dATAbAse.update_user_step(user_id, next_index)
        await handler_func(message, animate_func)
        return True

    return False
