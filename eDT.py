import re
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

public_link = None
user_steps = {}

def get_public_button():
    global public_link
    if public_link:
        if public_link.startswith("t.me") or public_link.startswith("http"):
            url_target = public_link if public_link.startswith("http") else f"https://{public_link}"
        else:
            clean_user = public_link.lstrip("@")
            url_target = f"https://t.me/{clean_user}"
        return InlineKeyboardButton(text="الاشتراك العلني", url=url_target)
    else:
        return InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8597653867")

async def handle_edt_command(message: types.Message):
    if message.chat.type != "private":
        return
        
    btn_set = InlineKeyboardButton(text="تعيين الرابط", switch_inline_query_current_chat="تعيين الرابط")
    btn_show = InlineKeyboardButton(text="عرض الاشتراك العلني", switch_inline_query_current_chat="عرض الاشتراك العلني")
    btn_del = InlineKeyboardButton(text="مسح", callback_data="del_edt")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_set], [btn_show], [btn_del]])
    await message.reply("تريد عرض الاشتراك العلني دوس زر\nعرض الاشتراك العلني\n\nهم لو تريد تعين رابط الزر دوس ع زر تعيين الرابط", reply_markup=kb)

async def process_edt_inputs(message: types.Message):
    global public_link
    chat_id = message.chat.id
    text = message.text.strip()
    
    if text == "تعيين الرابط":
        user_steps[chat_id] = "wait_url"
        await message.reply("ارسل يوزر / رابط القناة او الكروب\nيلا مولاي")
        return True
        
    if text == "عرض الاشتراك العلني":
        btn_pub = get_public_button()
        kb = InlineKeyboardMarkup(inline_keyboard=[[btn_pub]])
        await message.reply("مثل ماظاهر امامك زر الاشتراك العلني\nمثل مدتشوف دادي", reply_markup=kb)
        return True
        
    if user_steps.get(chat_id) == "wait_url":
        user_steps.pop(chat_id, None)
        
        is_url = "t.me" in text.lower() or text.lower().startswith("https")
        if is_url:
            public_link = text
            await message.reply("تم تعيين زر الاشتراك العلني مثل ماردت\nاعبد زبك يتاج راسي")
            return True
            
        clean_user = text.lstrip("@")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9_]{3,30}[a-zA-Z0-9]$", clean_user):
            if "_" in text and (text.startswith("_") or text.endswith("_")):
                await message.reply("اهو ليش تسوي هيج وياي ابوس زبك\nلاتعيدها مولاي")
                return True
            public_link = text
            await message.reply("تم تعيين زر الاشتراك العلني مثل ماردت\nاعبد زبك يتاج راسي")
        else:
            await message.reply("اهو ليش تسوي هيج وياي ابوس زبك\nلاتعيدها مولاي")
        return True
        
    return False

async def handle_edt_callback(callback: types.CallbackQuery):
    if callback.data == "del_edt":
        try:
            await callback.message.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
            if callback.message.reply_to_message:
                await callback.message.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.reply_to_message.message_id)
        except:
            pass
        await callback.answer()
