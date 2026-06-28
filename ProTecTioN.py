import os
import sys
import math
import asyncio
from aiogram import Router, F, Bot, Dispatcher
from aiogram.types import Message, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ReactionTypeEmoji
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, IS_ADMIN
from aiogram.filters import CHAT_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        sys.exit(1)
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    try:
        startup_msg = await bot.send_message(
            chat_id=8597653867,
            text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
        )
        await bot.set_message_reaction(
            chat_id=8597653867,
            message_id=startup_msg.message_id,
            reaction=[ReactionTypeEmoji(emoji="😭")]
        )
    except Exception:
        pass
    await dp.start_polling(bot)

router = Router()

db_roles = {}
bot_disabled_status = {}
custom_commands = {}
muted_users = {}
banned_users = {}
restricted_users = {}
user_last_message_time = {}
channel_button_url = "https://t.me/Telegram"

ROLE_LEVELS = {
    "عضو": 0, "مميز": 1, "مدير": 2, "منشئ": 3, "مطور": 4, "مطور ثانوي": 5, "مطور اساسي": 6
}

class CommandAliasState(StatesGroup):
    waiting_for_old_command = State()
    waiting_for_new_name = State()
    waiting_for_delete_command = State()

class BotEditState(StatesGroup):
    waiting_for_link = State()

async def get_user_role(chat_id: int, user_id: int, bot: Bot) -> str:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            return "مطور اساسي"
    except Exception:
        pass
    if chat_id in db_roles and user_id in db_roles[chat_id]:
        return db_roles[chat_id][user_id]
    return "عضو"

def get_role_with_al(role: str) -> str:
    mapping = {
        "مميز": "المميز", "مدير": "المدير", "منشئ": "المنشئ",
        "مطور": "المطور", "مطور ثانوي": "المطور الثانوي", "مطور اساسي": "المطور الأساسي", "عضو": "العضو"
    }
    return mapping.get(role, role)

def get_red_btn():
    target_url = channel_button_url
    if not target_url or target_url == "https://t.me/Telegram":
        target_url = "tg://user?id=8597653867"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="اشترك بالقناة", url=target_url)]
    ])

async def send_paginated_list(message: Message, user_list: list, title: str, page: int, allowed_user_id: int):
    items_per_page = 42
    total_pages = math.ceil(len(user_list) / items_per_page)
    text = f"{title}\n"
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_items = user_list[start_idx:end_idx]
    for i, uid in enumerate(current_items, start=start_idx + 1):
        text += f"*{i} [{uid}](tg://user?id={uid})\n"
    buttons = []
    if total_pages > 1 and page < total_pages - 1:
        buttons.append([InlineKeyboardButton(text="المزيد", callback_data=f"list_more:{title}:{page+1}:{allowed_user_id}")])
    buttons.append([InlineKeyboardButton(text="مسح", callback_data=f"list_delete:{allowed_user_id}", style="danger")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(message, Message):
        await message.reply(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(F.chat.type == "private", F.text == "ادت", F.from_user.id == 8597653867)
async def admin_edit_cmd(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="تعيين الرابط"), KeyboardButton(text="عرض الزر")]
    ], resize_keyboard=True)
    await message.reply("تريد تعين رابط الزر دوس تعيين الرابط\nتريد معاينة سريعة دوس عرض الزر", reply_markup=kb)

@router.message(F.chat.type == "private", F.text == "تعيين الرابط", F.from_user.id == 8597653867)
async def set_link_start(message: Message, state: FSMContext):
    await message.reply("ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", reply_markup=ReplyKeyboardRemove())
    await state.set_state(BotEditState.waiting_for_link)

@router.message(BotEditState.waiting_for_link, F.chat.type == "private")
async def process_link_input(message: Message, state: FSMContext):
    global channel_button_url
    text = message.text or ""
    if "t.me" in text or "https" in text or text.startswith("@"):
        channel_button_url = text
        await message.reply("تم تعيين زر الاشتراك المرفق\nصار مولاي")
    else:
        await message.reply("اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي")
    await state.clear()

@router.message(F.chat.type == "private", F.text == "عرض الزر", F.from_user.id == 8597653867)
async def view_btn_admin(message: Message):
    await message.reply("هاي معاينه سريعه للزر اليطلع بالكروب\nدتشوف عيني مو", reply_markup=get_red_btn())

@router.message(F.chat.type == "private")
async def handle_private_messages(message: Message, bot: Bot):
    if message.from_user.id == 8597653867 and message.text == "ادت":
        return
    user_id = message.from_user.id
    current_time = message.date.timestamp()
    user_last_message_time[user_id] = current_time
    await asyncio.sleep(3)
    if user_last_message_time.get(user_id) != current_time:
        return
    blue_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="المطور", url="tg://user?id=8597653867", style="primary")]
    ])
    await message.reply("اضغط هنا لمراسلة المطور والتحكم في البوت دادي", reply_markup=blue_keyboard)

@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=CHAT_MEMBER >> IS_ADMIN))
async def user_promoted_to_admin(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user_id = event.new_chat_member.user.id
    if chat_id not in db_roles:
        db_roles[chat_id] = {}
    db_roles[chat_id][user_id] = "مطور"

@router.my_chat_member()
async def bot_lost_admin(event: ChatMemberUpdated):
    if event.new_chat_member.status not in ["administrator", "creator"]:
        chat_id = event.chat.id
        if chat_id in db_roles: del db_roles[chat_id]
        if chat_id in bot_disabled_status: del bot_disabled_status[chat_id]
        if chat_id in custom_commands: del custom_commands[chat_id]
        if chat_id in muted_users: del muted_users[chat_id]
        if chat_id in banned_users: del banned_users[chat_id]
        if chat_id in restricted_users: del restricted_users[chat_id]

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"تفعيل", "تعطيل"}))
async def toggle_bot(message: Message, bot: Bot):
    sender_role = await get_user_role(message.chat.id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] == 0:
        return
    command = message.text
    chat_title = message.chat.title
    try:
        chat_admins = await bot.get_chat_administrators(message.chat.id)
        owner_id = next((admin.user.id for admin in chat_admins if admin.status == "creator"), message.from_user.id)
    except Exception:
        owner_id = message.from_user.id
        chat_admins = []
    blue_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="المطور", url=f"tg://user?id={owner_id}", style="primary")]
    ])
    if command == "تفعيل":
        bot_disabled_status[message.chat.id] = False
        members_count = await bot.get_chat_member_count(message.chat.id)
        text = f"تم تفعيل البوت\nالبوت يعمل الان في {chat_title}\nعدد المشرفين: {len(chat_admins)} عدد الاعضاء {members_count}"
        await message.reply(text, reply_markup=blue_keyboard)
    elif command == "تعطيل":
        bot_disabled_status[message.chat.id] = True
        text = "تم تعطيل البوت\nتنبيه البوت لايعمل الان"
        await message.reply(text, reply_markup=blue_keyboard)

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "اضف امر")
async def add_command_start(message: Message, state: FSMContext, bot: Bot):
    if bot_disabled_status.get(message.chat.id, False): return
    sender_role = await get_user_role(message.chat.id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] < ROLE_LEVELS["منشئ"]: return
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="إلغاء", callback_data=f"cancel_cmd:{message.from_user.id}:{message.message_id}", style="danger")]
    ])
    sent = await message.reply("ماهو الامر اللذي تريد تغيير تسميته", reply_markup=cancel_btn)
    await state.set_state(CommandAliasState.waiting_for_old_command)
    await state.update_data(origin_msg_id=message.message_id, bot_msg_id=sent.message_id, user_id=message.from_user.id)

@router.message(CommandAliasState.waiting_for_old_command, F.chat.type.in_({"group", "supergroup"}), F.text)
async def add_command_old(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if message.from_user.id != data.get("user_id"):
        return
    all_base_cmds = {
        "رفع مميز", "م", "رفع مدير", "مد", "رفع منشئ", "من", "رفع مطور", "مط", "رفع مطور ثانوي", "ثان",
        "تنزيل الكل", "تك", "كتم", "طرد", "نبذ", "تقييد", "تق", "مسح المكتومين", "؟", "مسح المنبوذين", "/", "مسح المقيدين", "-"
    }
    old_cmd = message.text
    chat_id = message.chat.id
    actual_base = old_cmd
    if chat_id in custom_commands and old_cmd in custom_commands[chat_id]:
        actual_base = custom_commands[chat_id][old_cmd]
    if actual_base not in all_base_cmds:
        sender_role = await get_user_role(chat_id, message.from_user.id, bot)
        green_btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=sender_role, url=f"tg://user?id={message.from_user.id}", style="success")]
        ])
        await message.reply("هذا الامر ليس له اثر", reply_markup=green_btn)
        await state.clear()
        return
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="إلغاء", callback_data=f"cancel_cmd:{message.from_user.id}:{message.message_id}", style="danger")]
    ])
    sent = await message.reply(f"ماذا تريد تسمية الامر {old_cmd}", reply_markup=cancel_btn)
    await state.set_state(CommandAliasState.waiting_for_new_name)
    await state.update_data(actual_base=actual_base, bot_msg_id=sent.message_id, origin_msg_id=message.message_id, user_id=message.from_user.id)

@router.message(CommandAliasState.waiting_for_new_name, F.chat.type.in_({"group", "supergroup"}), F.text)
async def add_command_new(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if message.from_user.id != data.get("user_id"):
        return
    new_name = message.text
    actual_base = data["actual_base"]
    chat_id = message.chat.id
    if chat_id not in custom_commands:
        custom_commands[chat_id] = {}
    custom_commands[chat_id][new_name] = actual_base
    sender_role = await get_user_role(chat_id, message.from_user.id, bot)
    role_formatted = get_role_with_al(sender_role)
    try:
        chat_admins = await bot.get_chat_administrators(chat_id)
        owner_id = next((admin.user.id for admin in chat_admins if admin.status == "creator"), message.from_user.id)
    except Exception:
        owner_id = message.from_user.id
    blue_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="المطور", url=f"tg://user?id={owner_id}", style="primary")]
    ])
    mention_sender = f"[{role_formatted}](tg://user?id={message.from_user.id})"
    await message.reply(f"اضف هذا {mention_sender} تسميه {new_name}", reply_markup=blue_keyboard, parse_mode="Markdown")
    await state.clear()

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "مسح امر")
async def delete_command_start(message: Message, state: FSMContext, bot: Bot):
    if bot_disabled_status.get(message.chat.id, False): return
    sender_role = await get_user_role(message.chat.id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] < ROLE_LEVELS["منشئ"]: return
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="إلغاء", callback_data=f"cancel_cmd:{message.from_user.id}:{message.message_id}", style="danger")]
    ])
    sent = await message.reply("شنو الامر التريد تزينه عزيزي", reply_markup=cancel_btn)
    await state.set_state(CommandAliasState.waiting_for_delete_command)
    await state.update_data(origin_msg_id=message.message_id, bot_msg_id=sent.message_id, user_id=message.from_user.id)

@router.message(CommandAliasState.waiting_for_delete_command, F.chat.type.in_({"group", "supergroup"}), F.text)
async def delete_command_exec(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if message.from_user.id != data.get("user_id"):
        return
    target_cmd = message.text
    chat_id = message.chat.id
    if chat_id not in custom_commands or target_cmd not in custom_commands[chat_id]:
        sender_role = await get_user_role(chat_id, message.from_user.id, bot)
        green_btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=sender_role, url=f"tg://user?id={message.from_user.id}", style="success")]
        ])
        await message.reply("هذه التسميه ليس لها اثر", reply_markup=green_btn)
        await state.clear()
        return
    del custom_commands[chat_id][target_cmd]
    try:
        chat_admins = await bot.get_chat_administrators(chat_id)
        owner_id = next((admin.user.id for admin in chat_admins if admin.status == "creator"), message.from_user.id)
    except Exception:
        owner_id = message.from_user.id
    blue_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="المطور", url=f"tg://user?id={owner_id}", style="primary")]
    ])
    await message.reply(f"تم مسح امر {target_cmd} عزيزي", reply_markup=blue_keyboard)
    await state.clear()

@router.callback_query(F.data.startswith("cancel_cmd:"))
async def cancel_command_action(callback: CallbackQuery, state: FSMContext, bot: Bot):
    _, allowed_user_id, _ = callback.data.split(":")
    if callback.from_user.id != int(allowed_user_id):
        await callback.answer("الامر مو الك/ج ابتعد/ي لا انيج امك/ج\nشلاع/ة العير", show_alert=True)
        return
    data = await state.get_data()
    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        if "origin_msg_id" in data:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=data["origin_msg_id"])
    except Exception:
        pass
    await state.clear()
    await callback.answer()

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"المكتومين عام", "المكتومين", "المنبوذين", "المقيدين"}))
async def list_punished_users(message: Message, bot: Bot):
    if bot_disabled_status.get(message.chat.id, False): return
    sender_role = await get_user_role(message.chat.id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] == 0: return
    cmd = message.text
    chat_id = message.chat.id
    if cmd in ["المكتومين", "المكتومين عام"]:
        user_list = list(muted_users.get(chat_id, set()))
        title = "المكتومين" if cmd == "المكتومين" else "المكتومين عام"
    elif cmd == "المنبوذين":
        user_list = list(banned_users.get(chat_id, set()))
        title = "المنبوذين"
    else:
        user_list = list(restricted_users.get(chat_id, set()))
        title = "المقيدين"
    if not user_list:
        await message.reply("الليسته فارغة عزيزي")
        return
    await send_paginated_list(message, user_list, title, 0, message.from_user.id)

@router.callback_query(F.data.startswith("list_more:"))
async def list_more_click(callback: CallbackQuery):
    _, title, next_page, allowed_user_id = callback.data.split(":")
    if callback.from_user.id != int(allowed_user_id):
        await callback.answer("الامر مو الك/ج ابتعد/ي لا انيج امك/ج\nشلاع/ة العير", show_alert=True)
        return
    next_page = int(next_page)
    chat_id = callback.message.chat.id
    if title in ["المكتومين", "المكتومين عام"]:
        user_list = list(muted_users.get(chat_id, set()))
    elif title == "المنبوذين":
        user_list = list(banned_users.get(chat_id, set()))
    else:
        user_list = list(restricted_users.get(chat_id, set()))
    await send_paginated_list(callback.message, user_list, title, next_page, int(allowed_user_id))
    await callback.answer()

@router.callback_query(F.data.startswith("list_delete:"))
async def list_delete_click(callback: CallbackQuery):
    _, allowed_user_id = callback.data.split(":")
    if callback.from_user.id != int(allowed_user_id):
        await callback.answer("الامر مو الك/ج ابتعد/ي لا انيج امك/ج\nشلاع/ة العير", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"تنظيف", "تن"}))
async def show_cleaning_panel(message: Message, bot: Bot):
    if bot_disabled_status.get(message.chat.id, False): return
    sender_role = await get_user_role(message.chat.id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] < ROLE_LEVELS["مدير"]: return
    uid = message.from_user.id
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="تنظيف الروابط", callback_data=f"clean:links:{uid}", style="primary")],
        [InlineKeyboardButton(text="تنظيف التعديلات", callback_data=f"clean:edits:{uid}", style="primary")],
        [InlineKeyboardButton(text="تنظيف اليوزرات", callback_data=f"clean:usernames:{uid}", style="primary")],
        [InlineKeyboardButton(text="تنظيف التفاعلات", callback_data=f"clean:reactions:{uid}", style="danger")],
        [InlineKeyboardButton(text="تنظيف الصوتيات", callback_data=f"clean:audios:{uid}", style="danger")],
        [InlineKeyboardButton(text="تنظيف الفويسات", callback_data=f"clean:voices:{uid}", style="danger")],
        [InlineKeyboardButton(text="الكل", callback_data=f"clean:all:{uid}", style="success")]
    ])
    await message.reply(text=".", reply_markup=keyboard)

@router.callback_query(F.data.startswith("clean:"))
async def handle_cleaning_buttons(callback: CallbackQuery, bot: Bot):
    _, mode, allowed_user_id = callback.data.split(":")
    if callback.from_user.id != int(allowed_user_id):
        await callback.answer("الامر مو الك/ج ابتعد/ي لا انيج امك/ج\nشلاع/ة العير", show_alert=True)
        return
    await callback.message.delete()
    chat_id = callback.message.chat.id
    bot_info = await bot.get_me()
    count = 0
    try:
        async for msg in bot.get_chat_history(chat_id=chat_id, limit=10000):
            if msg.from_user and msg.from_user.id == bot_info.id:
                continue
            should_delete = False
            if mode == "links":
                if msg.text or msg.caption:
                    txt = msg.text or msg.caption
                    if "t.me" in txt or "https" in txt:
                        should_delete = True
            elif mode == "edits":
                if msg.edit_date and (msg.photo or msg.video):
                    should_delete = True
            elif mode == "usernames":
                if msg.text or msg.caption:
                    txt = msg.text or msg.caption
                    if "@" in txt:
                        should_delete = True
            elif mode == "reactions":
                if msg.reactions:
                    try:
                        await bot.set_message_reaction(chat_id=chat_id, message_id=msg.message_id, reaction=[])
                        count += 1
                    except Exception:
                        pass
            elif mode == "audios":
                if msg.audio:
                    should_delete = True
            elif mode == "voices":
                if msg.voice:
                    should_delete = True
            elif mode == "all":
                if msg.voice:
                    continue
                if msg.audio:
                    should_delete = True
                elif msg.text or msg.caption:
                    txt = msg.text or msg.caption
                    if "t.me" in txt or "https" in txt or "@" in txt:
                        should_delete = True
                elif msg.edit_date and (msg.photo or msg.video):
                    should_delete = True
                if msg.reactions:
                    try:
                        await bot.set_message_reaction(chat_id=chat_id, message_id=msg.message_id, reaction=[])
                        count += 1
                    except Exception:
                        pass
            if should_delete:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                    count += 1
                except Exception:
                    pass
    except Exception:
        pass
    if mode in ["all", "links", "edits", "usernames", "reactions", "audios", "voices"]:
        await bot.send_message(chat_id=chat_id, text=f"تم مسح {count} من الميديا المرسلة دادي\nشاتنا صار نظيف يلمع")
    await callback.answer()

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"امسح", "ام"}))
async def clear_media_cmd(message: Message, bot: Bot):
    if bot_disabled_status.get(message.chat.id, False): return
    sender_role = await get_user_role(message.chat.id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] < ROLE_LEVELS["مدير"]: return
    if message.reply_to_message:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            await bot.delete_message(chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
        except Exception:
            pass
        return
    chat_id = message.chat.id
    bot_info = await bot.get_me()
    count = 0
    try:
        async for msg in bot.get_chat_history(chat_id=chat_id, limit=10000):
            if msg.from_user and msg.from_user.id == bot_info.id:
                continue
            if msg.video or msg.photo or msg.sticker or msg.animation or msg.document or msg.location or msg.contact or msg.video_note:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                    count += 1
                except Exception:
                    pass
    except Exception:
        pass
    await message.reply(f"تم مسح {count} من الميديا المرسلة دادي\nشاتنا صار نظيف يلمع")

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.startswith("تنظيف "))
async def clear_num_messages(message: Message, bot: Bot):
    if bot_disabled_status.get(message.chat.id, False): return
    sender_role = await get_user_role(message.chat.id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] < ROLE_LEVELS["مطور"]: return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit(): return
    num = int(parts[1])
    if num > 3000: num = 3000
    chat_id = message.chat.id
    start_id = message.message_id
    count = 0
    for msg_id in range(start_id, start_id - num - 1, -1):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            count += 1
        except Exception:
            pass
    try:
        chat_admins = await bot.get_chat_administrators(chat_id)
        owner_id = next((admin.user.id for admin in chat_admins if admin.status == "creator"), message.from_user.id)
    except Exception:
        owner_id = message.from_user.id
    blue_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="المطور", url=f"tg://user?id={owner_id}", style="primary")]
    ])
    await bot.send_message(chat_id=chat_id, text=f"تم تنظيف {count} من رسايل الشات\nتدلل عيني", reply_markup=blue_keyboard)

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def main_group_handler(message: Message, bot: Bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state in [CommandAliasState.waiting_for_old_command, CommandAliasState.waiting_for_new_name, CommandAliasState.waiting_for_delete_command]:
        return
    if bot_disabled_status.get(message.chat.id, False): return
    text = message.text
    chat_id = message.chat.id
    if text in ["المطور", "المالك"]:
        try:
            chat_admins = await bot.get_chat_administrators(chat_id)
            owner_id = next((admin.user.id for admin in chat_admins if admin.status == "creator"), 8597653867)
        except Exception:
            owner_id = 8597653867
        blue_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="المطور", url=f"tg://user?id={owner_id}", style="primary")]
        ])
        await message.reply("اضغط هنا لمراسلة المطور والتحكم في البوت دادي", reply_markup=blue_keyboard)
        return
    if chat_id in custom_commands and text in custom_commands[chat_id]:
        text = custom_commands[chat_id][text]
    all_commands = {
        "رفع مميز", "م", "رفع مدير", "مد", "رفع منشئ", "من", "رفع مطور", "مط", "رفع مطور ثانوي", "ثان",
        "تنزيل الكل", "تك", "كتم", "طرد", "نبذ", "تقييد", "تق", "مسح المكتومين", "؟", "مسح المنبوذين", "/", "مسح المقيدين", "-"
    }
    if text not in all_commands: return
    sender_role = await get_user_role(chat_id, message.from_user.id, bot)
    if ROLE_LEVELS[sender_role] == 0: return 
    if not message.reply_to_message:
        await message.reply("لن يعمل الامر مادام لم تقم\nبعمل ريبلاي")
        return
    target_id = message.reply_to_message.from_user.id
    target_role = await get_user_role(chat_id, target_id, bot)
    if message.from_user.id == target_id:
        await message.reply("لا تستطيع تنزيل او رفع او معاقبه\nنفسك عزيزي")
        return
    sender_level = ROLE_LEVELS[sender_role]
    target_level = ROLE_LEVELS[target_role]
    verb_mapping = {"كتم": "بكتمه", "طرد": "بطرده", "تقييد": "bتقييده", "تق": "بتقييده", "نبذ": "bنبذه"}
    current_verb = verb_mapping.get(text, "بمعاقبته")
    if target_role == "مطور اساسي":
        await message.reply(f"كل عقلك تريد {text} لا تفتر هواي اكعد\nعلمود ماتناج تكوم تمشي صفح")
        return
    if text in ["تنزيل الكل", "تك"]:
        if sender_level < target_level:
            await message.reply("رتبته اعلى من رتبتك لا يمكنك\nان تقوم بتنزيله")
            return
        elif sender_level == target_level:
            await message.reply("لا تستطيع تنزيل او رفع او معاقبته\nلان رتبته مشابهة لك", reply_markup=get_red_btn())
            return
        if chat_id in db_roles and target_id in db_roles[chat_id]:
            del db_roles[chat_id][target_id]
        await message.reply(f"رفعته عضو مثل ماردت تاج راسي وممنون الك")
        return
    upload_commands = {
        "رفع مميز": "مميز", "م": "مميز", "رفع مدير": "مدير", "مد": "مدير",
        "رفع منشئ": "منشئ", "من": "منشئ", "رفع مطور": "مطور", "مط": "مطور",
        "رفع مطور ثانوي": "مطور ثانوي", "ثان": "مطور ثانوي"
    }
    if text in upload_commands:
        new_role = upload_commands[text]
        if sender_level == target_level:
            await message.reply("لا تستطيع تنزيل او رفع او معاقبته\nلان رتبته مشابهة لك", reply_markup=get_red_btn())
            return
        if sender_level < target_level or sender_level <= ROLE_LEVELS[new_role]:
            return
        if chat_id not in db_roles: db_roles[chat_id] = {}
        db_roles[chat_id][target_id] = new_role
        await message.reply(f"رفعته {new_role} مثل ماردت تاج راسي وممنون الك")
        return
    if target_level > 0:
        if sender_level > target_level:
            await message.reply("قم بتنزيله اولا لان الامر لن يعمل\nمادام يمتلك رتبه")
            return
        elif sender_level < target_level:
            await message.reply(f"رتبته اعلى من رتبتك لا يمكنك\nان تقوم {current_verb}")
            return
        else:
            await message.reply("لا تستطيع تنزيل او رفع او معاقبته\nلان رتبته مشابهة لك", reply_markup=get_red_btn())
            return
    action_performed = None
    if text == "كتم" and sender_level >= ROLE_LEVELS["مدير"]:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=target_id, permissions=ChatPermissions(can_send_messages=False))
        if chat_id not in muted_users: muted_users[chat_id] = set()
        muted_users[chat_id].add(target_id)
        action_performed = "كتم"
    elif text == "طرد" and sender_level >= ROLE_LEVELS["مطور"]:
        await bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
        await bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
        action_performed = "طرد"
    elif text == "نبذ" and sender_level >= ROLE_LEVELS["مطور ثانوي"]:
        await bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
        if chat_id not in banned_users: banned_users[chat_id] = set()
        banned_users[chat_id].add(target_id)
        action_performed = "نبذ"
    elif text in ["تقييد", "تق"] and sender_level >= ROLE_LEVELS["مطور ثانوي"]:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=target_id, permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=False, can_add_web_page_previews=False))
        if chat_id not in restricted_users: restricted_users[chat_id] = set()
        restricted_users[chat_id].add(target_id)
        action_performed = "تقييد"
    elif text in ["مسح المكتومين", "؟"] and sender_level >= ROLE_LEVELS["مدير"]:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=target_id, permissions=ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
        if chat_id in muted_users and target_id in muted_users[chat_id]: muted_users[chat_id].remove(target_id)
        await message.reply("تم مسح المكتومين")
        return
    elif text in ["مسح المنبوذين", "/"] and sender_level >= ROLE_LEVELS["مطور ثانوي"]:
        await bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
        if chat_id in banned_users and target_id in banned_users[chat_id]: banned_users[chat_id].remove(target_id)
        await message.reply("تم مسح المنبوذين")
        return
    elif text in ["مسح المقيدين", "-"] and sender_level >= ROLE_LEVELS["مطور ثانوي"]:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=target_id, permissions=ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
        if chat_id in restricted_users and target_id in restricted_users[chat_id]: restricted_users[chat_id].remove(target_id)
        await message.reply("تم مسح المقيدين")
        return
    if action_performed:
        green_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="شلاع/ة العير", url=f"tg://user?id={target_id}", style="success")]
        ])
        mention_sender = f"[{sender_role}](tg://user?id={message.from_user.id})"
        response_text = f"تم {action_performed} هذا المنيوج عزيزي / {mention_sender}"
        await message.reply(response_text, reply_markup=green_keyboard, parse_mode="Markdown")

if __name__ == "__main__":
    asyncio.run(main())
