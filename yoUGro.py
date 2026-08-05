import os
import sqlite3
from aiogram import Router, F, Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

DB_PATH = os.environ.get("DATABASE_PATH", "bot.db")

db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS group_roles (
    chat_id INTEGER,
    user_id INTEGER,
    role TEXT,
    PRIMARY KEY (chat_id, user_id)
)
""")
conn.commit()

def get_user_role_db(chat_id, user_id):
    cursor.execute("SELECT role FROM group_roles WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    row = cursor.fetchone()
    return row[0] if row else None

def set_user_role_db(chat_id, user_id, role):
    if role is None:
        cursor.execute("DELETE FROM group_roles WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    else:
        cursor.execute("INSERT OR REPLACE INTO group_roles (chat_id, user_id, role) VALUES (?, ?, ?)", (chat_id, user_id, role))
    conn.commit()

def get_all_vip_db(chat_id):
    cursor.execute("SELECT user_id FROM group_roles WHERE chat_id = ? AND role = 'مميز'", (chat_id,))
    return [row[0] for row in cursor.fetchall()]

def get_all_admins_db(chat_id):
    cursor.execute("SELECT user_id FROM group_roles WHERE chat_id = ? AND role = 'ادمن'", (chat_id,))
    return [row[0] for row in cursor.fetchall()]

router = Router()

async def get_user_role(bot: Bot, chat_id: int, user_id: int):
    db_role = get_user_role_db(chat_id, user_id)
    if db_role:
        return db_role
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            return "مالك"
        elif member.status == "administrator":
            return "ادمن"
    except Exception:
        pass
    return "عضو"

def get_group_buttons(user_id: int):
    btn_dev = InlineKeyboardButton(text="المطور", url="tg://openmessage?user_id=8436425159", style="primary")
    btn_meow = InlineKeyboardButton(text="ميو", url=f"tg://openmessage?user_id={user_id}", style="danger")
    return InlineKeyboardMarkup(inline_keyboard=[[btn_dev], [btn_meow]])

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "رتبتي")
async def my_rank_handler(message: types.Message, bot: Bot):
    role = await get_user_role(bot, message.chat.id, message.from_user.id)
    user_md = f"[{message.from_user.id}](tg://user?id={message.from_user.id})"
    text = f"¹# - رتبتك مولاي {user_md}\n{role}"
    await message.reply(text, parse_mode="Markdown", reply_markup=get_group_buttons(message.from_user.id))

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"م", "رفع مميز"}))
async def promote_vip_handler(message: types.Message, bot: Bot):
    if not message.reply_to_message:
        return
    issuer_role = await get_user_role(bot, message.chat.id, message.from_user.id)
    if issuer_role not in ["مالك", "ادمن"]:
        return
    
    target_user = message.reply_to_message.from_user
    set_user_role_db(message.chat.id, target_user.id, "مميز")
    
    issuer_md = f"[{message.from_user.id}](tg://user?id={message.from_user.id})"
    target_md = f"[{target_user.id}](tg://user?id={target_user.id})"
    
    text = f"{issuer_md}\n¹# - تم رفعه مميز\n{target_md} تاج راسي"
    await message.reply(text, parse_mode="Markdown", reply_markup=get_group_buttons(message.from_user.id))

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"اد", "رفع ادمن"}))
async def promote_admin_handler(message: types.Message, bot: Bot):
    if not message.reply_to_message:
        return
    issuer_role = await get_user_role(bot, message.chat.id, message.from_user.id)
    if issuer_role != "مالك":
        return
    
    target_user = message.reply_to_message.from_user
    set_user_role_db(message.chat.id, target_user.id, "ادمن")
    
    issuer_md = f"[{message.from_user.id}](tg://user?id={message.from_user.id})"
    target_md = f"[{target_user.id}](tg://user?id={target_user.id})"
    
    text = f"{issuer_md}\n¹# - تم رفعه ادمن\n{target_md} تاج راسي"
    await message.reply(text, parse_mode="Markdown", reply_markup=get_group_buttons(message.from_user.id))

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "تك")
async def demote_handler(message: types.Message, bot: Bot):
    if not message.reply_to_message:
        return
    issuer_role = await get_user_role(bot, message.chat.id, message.from_user.id)
    if issuer_role not in ["مالك", "ادمن"]:
        return
        
    target_user = message.reply_to_message.from_user
    target_role = await get_user_role(bot, message.chat.id, target_user.id)
    
    if target_role == "ادمن" and issuer_role != "مالك":
        return
        
    if target_role not in ["مميز", "ادمن"]:
        return

    set_user_role_db(message.chat.id, target_user.id, None)
    
    issuer_md = f"[{message.from_user.id}](tg://user?id={message.from_user.id})"
    target_md = f"[{target_user.id}](tg://user?id={target_user.id})"
    
    text = f"{issuer_md}\n¹# - تم تنزيل رتبته\n{target_md}"
    await message.reply(text, parse_mode="Markdown", reply_markup=get_group_buttons(message.from_user.id))

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "المميزين")
async def list_vips_handler(message: types.Message, bot: Bot):
    issuer_role = await get_user_role(bot, message.chat.id, message.from_user.id)
    if issuer_role not in ["مالك", "ادمن", "مميز"]:
        return
        
    vips = get_all_vip_db(message.chat.id)
    if not vips:
        return
        
    lines = []
    for uid in vips:
        try:
            chat_mem = await bot.get_chat_member(message.chat.id, uid)
            u = chat_mem.user
            user_md = f"[{u.id}](tg://user?id={u.id})"
            username_str = f"||@{u.username}||" if u.username else "||@||"
            lines.append(f"¹# - {user_md}\n{username_str}")
        except Exception:
            user_md = f"[{uid}](tg://user?id={uid})"
            lines.append(f"¹# - {user_md}\n||@||")
            
    res_text = "\n\n".join(lines)
    await message.reply(res_text, parse_mode="Markdown", reply_markup=get_group_buttons(message.from_user.id))

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "الادمن")
async def list_admins_handler(message: types.Message, bot: Bot):
    issuer_role = await get_user_role(bot, message.chat.id, message.from_user.id)
    if issuer_role not in ["مالك", "ادمن"]:
        return
        
    admins = get_all_admins_db(message.chat.id)
    try:
        chat_obj = await bot.get_chat(message.chat.id)
        admins_list = await bot.get_chat_administrators(message.chat.id)
        creator_id = None
        for adm in admins_list:
            if adm.status == "creator":
                creator_id = adm.user.id
                break
        
        all_admin_ids = []
        if creator_id:
            all_admin_ids.append(creator_id)
        for aid in admins:
            if aid not in all_admin_ids:
                all_admin_ids.append(aid)
    except Exception:
        all_admin_ids = admins

    if not all_admin_ids:
        return
        
    lines = []
    for uid in all_admin_ids:
        try:
            chat_mem = await bot.get_chat_member(message.chat.id, uid)
            u = chat_mem.user
            user_md = f"[{u.id}](tg://user?id={u.id})"
            username_str = f"||@{u.username}||" if u.username else "||@||"
            lines.append(f"¹# - {user_md}\n{username_str}")
        except Exception:
            user_md = f"[{uid}](tg://user?id={uid})"
            lines.append(f"¹# - {user_md}\n||@||")
            
    res_text = "\n\n".join(lines)
    await message.reply(res_text, parse_mode="Markdown", reply_markup=get_group_buttons(message.from_user.id))
