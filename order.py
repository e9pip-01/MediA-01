import asyncio
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType

import strings
import database

order_router = Router()

@order_router.callback_query(F.data.startswith("btn_"))
async def handle_inline_buttons(callback: types.CallbackQuery):
    if not callback.message or not isinstance(callback.message, types.Message):
        await callback.answer()
        return

    orig_msg = callback.message.reply_to_message
    data_parts = callback.data.split("_")
    action = data_parts[1]
    invoker_id = int(data_parts[2])
    user_id = callback.from_user.id
    
    try:
        member = await callback.message.chat.get_member(user_id)
        is_admin_or_owner = member.status in ['creator', 'administrator']
    except Exception:
        is_admin_or_owner = False

    if not is_admin_or_owner:
        await callback.answer(strings.NOT_ALLOWED_ADMIN if hasattr(strings, 'NOT_ALLOWED_ADMIN') else "¹# - هذه الازرار للمشرفين والمالكين فقط\nتوكل لا انيج امك ابن عيري", show_alert=True)
        return

    if user_id != invoker_id:
        await callback.answer(strings.NOT_ALLOWED_INVOKER if hasattr(strings, 'NOT_ALLOWED_INVOKER') else "¹# - هذه الازرار مصممه لتفهم نقرات من\nاستدعاها فقط", show_alert=True)
        return

    if action == "delete":
        try:
            await callback.message.delete()
            if orig_msg:
                await orig_msg.delete()
        except Exception:
            pass
        await callback.answer()
        return
