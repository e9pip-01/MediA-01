import asyncio
import re
import os
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType

import STriNGs
import dATAbAse

order_router = Router()

whisper_data = {}
active_whisper_sessions = {}

def get_target_id_from_text(text: str, message: types.Message) -> tuple:
    target_id = None
    target_username = None
    
    parts = re.split(r'\s+', text)
    cmd_index = -1
    for i, part in enumerate(parts):
        if part in ["همسة", "همسه", "اهمس", "همس"]:
            cmd_index = i
            break
            
    if cmd_index == -1 or cmd_index + 1 >= len(parts):
        return None, None

    arg = parts[cmd_index + 1]
    
    if arg.startswith("@"):
        target_username = arg.replace("@", "").strip()
        return None, target_username
        
    if arg.isdigit():
        target_id = int(arg)
        return target_id, None

    if message.entities:
        for entity in message.entities:
            if entity.type == "text_link" and entity.url.startswith("tg://user?id="):
                try:
                    target_id = int(entity.url.split("id=")[1])
                    return target_id, None
                except Exception:
                    pass
    return None, None

@order_router.callback_query(F.data.startswith("btn_"))
async def handle_inline_buttons(callback: types.CallbackQuery, bot: Bot, trigger_delayed_reaction, safe_send_food_emoji, handle_message):
    if not callback.message or not isinstance(callback.message, types.Message):
        await callback.answer()
        return

    orig_msg = callback.message.reply_to_message
    if not orig_msg:
        await callback.answer("عذراً، لم يتم العثور على الرسالة الأصلية.", show_alert=True)
        return

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
        await callback.answer("¹# - هذه الازرار للمشرفين والمالكين فقط\nتوكل لا انيج امك ابن عيري", show_alert=True)
        return

    if user_id != invoker_id:
        await callback.answer("¹# - هذه الازرار مصممه لتفهم نقرات من\nاستدعاها فقط", show_alert=True)
        return

    if action == "delete":
        try:
            await callback.message.delete()
            await orig_msg.delete()
        except Exception:
            pass
        await callback.answer()
        return

@order_router.message(lambda msg: any(x in msg.text for x in ["همسة", "همسه", "اهمس", "همس"]) if msg.text else False)
async def process_whisper_command(message: types.Message, bot: Bot, trigger_delayed_reaction, safe_send_food_emoji):
    chat_type = message.chat.type
    if chat_type == ChatType.PRIVATE:
        return

    text = message.text.strip()
    sender_id = message.from_user.id
    target_id = None
    target_username = None

    if message.reply_to_message:
        if message.reply_to_message.from_user.is_bot:
            return
        target_id = message.reply_to_message.from_user.id
    else:
        target_id, target_username = get_target_id_from_text(text, message)

    if not target_id and not target_username:
        return

    if target_username and not target_id:
        try:
            chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=f"@{target_username}")
            target_id = chat_member.user.id
        except Exception:
            try:
                target_id = int(target_username)
            except Exception:
                return

    if not target_id:
        return

    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))
    
    secret_key = f"whsp_{sender_id}_{target_id}_{message.message_id}"
    
    kb = [[types.InlineKeyboardButton(text="اهمس", callback_data=secret_key, style="primary")]]
    markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
    
    sent = await message.reply("اضغط على زر اهمس واكتب همستك\nبشات البوت", reply_markup=markup)
    asyncio.create_task(trigger_delayed_reaction(bot, sent.chat.id, sent.message_id))
    asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))

@order_router.callback_query(F.data.startswith("whsp_"))
async def handle_whisper_click(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    sender_id = int(parts[1])
    target_id = int(parts[2])
    orig_msg_id = int(parts[3])

    if user_id != sender_id:
        await callback.answer("الزر ليس لك لتهمس منه.", show_alert=True)
        return

    bot_info = await bot.get_me()
    url = f"https://t.me/{bot_info.username}?start={callback.data}"
    
    await callback.answer(url, show_alert=True)

@order_router.callback_query(F.data.startswith("showwhsp_"))
async def show_whisper_content(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    target_id = int(parts[2])
    session_key = "_".join(parts[1:])

    if user_id != target_id:
        await callback.answer("الهمسة مو الك/ج ءتدعبل/ي\nعزيزي", show_alert=True)
        return

    content = whisper_data.get(session_key, "تم انتهاء صلاحية الهمسة أو حذفها.")
    await callback.answer(content, show_alert=True)

async def handle_start_whisper_session(message: types.Message, payload: str, bot: Bot, trigger_delayed_reaction, safe_send_food_emoji):
    user_id = message.from_user.id
    parts = payload.split("_")
    sender_id = int(parts[1])
    target_id = int(parts[2])
    orig_msg_id = int(parts[3])

    if user_id != sender_id:
        return

    sent_ask = await message.reply("اكتب همستك وراح يتم ارسالها للمقصود\nارسالها له")
    asyncio.create_task(trigger_delayed_reaction(bot, sent_ask.chat.id, sent_ask.message_id))
    
    session_key = f"{sender_id}_{target_id}_{orig_msg_id}"
    active_whisper_sessions[user_id] = {
        "session_key": session_key,
        "target_id": target_id,
        "orig_msg_id": orig_msg_id,
        "chat_id": parts[4] if len(parts) > 4 else None
    }
    
    asyncio.create_task(whisper_timeout_task(user_id))

async def whisper_timeout_task(user_id: int):
    await asyncio.sleep(180)
    if user_id in active_whisper_sessions:
        del active_whisper_sessions[user_id]

async def process_whisper_input(message: types.Message, bot: Bot, trigger_delayed_reaction, safe_send_food_emoji) -> bool:
    user_id = message.from_user.id
    if user_id not in active_whisper_sessions:
        return False

    session = active_whisper_sessions[user_id]
    session_key = session["session_key"]
    target_id = session["target_id"]
    orig_msg_id = session["orig_msg_id"]
    
    whisper_text = message.text
    whisper_data[session_key] = whisper_text
    
    del active_whisper_sessions[user_id]
    
    sender_link = f"t.me/user?id={user_id}"
    if message.from_user.username:
        sender_link = f"https://t.me/{message.from_user.username}"
        
    sender_markdown = f"<a href='{sender_link}'>هذا</a>"
    
    text_to_send = f"اكو همسة الك/ج يبعَدي\nمن #¹ {sender_markdown}"
    
    kb = [[types.InlineKeyboardButton(text="هاي همستك/ج", callback_data=f"showwhsp_{session_key}", style="danger")]]
    markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
    
    try:
        sent_whisper = await bot.send_message(
            chat_id=target_id,
            text=text_to_send,
            reply_markup=markup,
            parse_mode="HTML"
        )
        asyncio.create_task(trigger_delayed_reaction(bot, sent_whisper.chat.id, sent_whisper.message_id))
    except Exception:
        pass

    sent_done = await message.reply("تم إرسال الهمسة انطيني امص زبك\nودلل/ي يبعَدي")
    asyncio.create_task(trigger_delayed_reaction(bot, sent_done.chat.id, sent_done.message_id))
    asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
    return True
