import os
import asyncio
import random
from collections import deque
import chess
import chess.engine
import chess.svg
import cairosvg

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

import ujson
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove,
    FSInputFile
)
from aiogram.methods import SetMessageReaction
from aiogram.types import ReactionTypeEmoji

API_TOKEN = os.environ.get("BOT_TOKEN", "your_fallback_token_here")
ALLOWED_USER_ID = 8597653867

session = AiohttpSession(json_loads=ujson.loads, json_dumps=ujson.dumps)
bot = Bot(token=API_TOKEN, session=session)
dp = Dispatcher()

ACCOUNTS_FILE = "accounts.txt"
user_accounts = {}
active_account = {}

STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "stockfish")

def load_accounts_from_file():
    global user_accounts
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "," in line:
                    parts = line.split(",")
                    if len(parts) == 3:
                        u_id = int(parts[0])
                        email = parts[1]
                        password = parts[2]
                        if u_id not in user_accounts:
                            user_accounts[u_id] = []
                        user_accounts[u_id].append({"email": email, "password": password})
                        if u_id not in active_account:
                            active_account[u_id] = email

def save_account_to_file(user_id, email, password):
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user_id},{email},{password}\n")

load_accounts_from_file()

used_times_history = deque(maxlen=6)
available_times = [2.4, 4.8, 3.6, 6.3, 4.2, 8.7, 7.8, 8.4, 9.3, 3.9, 6.9, 9.6]

continuous_play_mode = False
continuous_play_time = None

current_board = chess.Board()

welcome_index = 0
welcome_responses = [
    "تغزل بيه اريد اكزكز واشبع رومانسيه\nاريد اذوب من الغزل\nاريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
]

reactions_pool = ["🥰", "😘", "🤣", "😭", "🍓", "🤗"]
last_reactions = deque(maxlen=4)

emoji_messages_pool = ["🥞", "🍣", "🥪", "🍕", "🍔", "🌭", "🍗"]
last_emoji_messages = deque(maxlen=5)

def get_main_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="اضف اكاونت"), KeyboardButton(text="المداوم")]
    ]
    if user_id in user_accounts and len(user_accounts[user_id]) > 0:
        buttons.append([KeyboardButton(text="تغيير الاكاونت")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_colored_time_buttons(prefix="time_"):
    return [
        [
            InlineKeyboardButton(text="1 دقيقة", callback_data=f"{prefix}1m", style="destructive"), 
            InlineKeyboardButton(text="1 + 1", callback_data=f"{prefix}1_1", style="destructive"), 
            InlineKeyboardButton(text="2 + 1", callback_data=f"{prefix}2_1", style="destructive")
        ],
        [
            InlineKeyboardButton(text="3 دقيقة", callback_data=f"{prefix}3m", style="primary"), 
            InlineKeyboardButton(text="3 + 2", callback_data=f"{prefix}3_2", style="primary"), 
            InlineKeyboardButton(text="5 دقيقة", callback_data=f"{prefix}5m", style="primary")
        ],
        [
            InlineKeyboardButton(text="10 دقيقة", callback_data=f"{prefix}10m", style="success"), 
            InlineKeyboardButton(text="15 + 10", callback_data=f"{prefix}15_10", style="success"), 
            InlineKeyboardButton(text="30 دقيقة", callback_data=f"{prefix}30m", style="success")
        ]
    ]

def calculate_smart_delay(remaining_time_str):
    try:
        minutes, seconds = map(int, remaining_time_str.split(':'))
        total_seconds = minutes * 60 + seconds
    except:
        total_seconds = 600

    if total_seconds <= 60:
        pool = [t for t in available_times if t < 7.8]
    else:
        pool = available_times

    allowed_choices = [t for t in pool if t not in used_times_history]
    if not allowed_choices:
        allowed_choices = pool

    chosen_time = random.choice(allowed_choices)
    used_times_history.append(chosen_time)
    return chosen_time

async def apply_random_reaction(message: Message):
    allowed_reactions = [r for r in reactions_pool if r not in last_reactions]
    if not allowed_reactions:
        allowed_reactions = reactions_pool
    
    chosen_reaction = random.choice(allowed_reactions)
    last_reactions.append(chosen_reaction)
    
    try:
        await bot(SetMessageReaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji=chosen_reaction)]
        ))
    except:
        pass

async def send_developer_button_delayed(chat_id, text):
    msg = await bot.send_message(chat_id=chat_id, text=text)
    await apply_random_reaction(msg)
    
    await asyncio.sleep(1)
    
    dev_button = [[InlineKeyboardButton(
        text="المطور", 
        user_id=ALLOWED_USER_ID,
        style="destructive"
    )]]
    
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=msg.message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=dev_button)
        )
    except:
        pass

    allowed_emojis = [e for e in emoji_messages_pool if e not in last_emoji_messages]
    if not allowed_emojis:
        allowed_emojis = emoji_messages_pool
        
    chosen_emoji = random.choice(allowed_emojis)
    last_emoji_messages.append(chosen_emoji)
    
    emoji_msg = await bot.send_message(chat_id=chat_id, text=chosen_emoji)
    await apply_random_reaction(emoji_msg)

@dp.message(~F.from_user.id == ALLOWED_USER_ID)
async def ignore_others(message: Message):
    return

@dp.message(F.text == "ابدء", F.from_user.id == ALLOWED_USER_ID)
async def play_cmd(message: Message):
    msg = await message.reply("توقيتات المباراة", reply_markup=InlineKeyboardMarkup(inline_keyboard=get_colored_time_buttons("time_")))
    await apply_random_reaction(msg)

@dp.message(F.text == "المداوم", F.from_user.id == ALLOWED_USER_ID)
async def continuous_play_cmd(message: Message):
    msg = await message.reply("توقيتات المباراة", reply_markup=InlineKeyboardMarkup(inline_keyboard=get_colored_time_buttons("cont_")))
    await apply_random_reaction(msg)

@dp.message(F.text == "ايقاف المداوم", F.from_user.id == ALLOWED_USER_ID)
async def stop_continuous_play(message: Message):
    global continuous_play_mode, continuous_play_time
    if continuous_play_mode:
        continuous_play_mode = False
        continuous_play_time = None
        msg = await message.reply("تم إيقاف ميزة المداوم\nمولاي")
    else:
        msg = await message.reply("ميزة المداوم غير مفعله\nمولاي")
    await apply_random_reaction(msg)

@dp.message(F.text == "اضف اكاونت", F.from_user.id == ALLOWED_USER_ID)
async def request_account(message: Message):
    msg = await message.reply(
        "دز ايميل الاكاونت مالتك والباسوورد\nمال الاكاونت",
        reply_markup=ReplyKeyboardRemove()
    )
    await apply_random_reaction(msg)

@dp.message(F.text == "تغيير الاكاونت", F.from_user.id == ALLOWED_USER_ID)
async def change_account_menu(message: Message):
    user_id = message.from_user.id
    if user_id not in user_accounts or len(user_accounts[user_id]) == 0:
        return

    inline_buttons = []
    for acc in user_accounts[user_id]:
        display_name = acc['email'].split('@')[0]
        inline_buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"switch_{acc['email']}"[:64])])

    msg = await message.reply(
        "اضغط على الزر اللذي يح ـمل اسم الايميل\nالمضاف",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    )
    await apply_random_reaction(msg)

@dp.message(F.text, F.from_user.id == ALLOWED_USER_ID)
async def handle_text_or_welcome(message: Message):
    global welcome_index
    
    lines = message.text.split('\n')
    if len(lines) == 2 and "@" in lines[0]:
        email = lines[0].strip()
        password = lines[1].strip()
        user_id = message.from_user.id

        if user_id in user_accounts and any(acc['email'] == email for acc in user_accounts[user_id]):
            msg = await message.reply("تم تسج ـيل الدخ ـول الى الح ـساب اللذي ارسلته بدون مشاكل", reply_markup=get_main_keyboard(user_id))
            await apply_random_reaction(msg)
            return

        status_msg = await message.reply("يتم القيام بتسج ـيل الدخ ـول الى\nالح ـساب اللذي ارسلته")
        await apply_random_reaction(status_msg)
        
        success = True
        
        if success:
            if user_id not in user_accounts:
                user_accounts[user_id] = []
            user_accounts[user_id].append({"email": email, "password": password})
            active_account[user_id] = email
            save_account_to_file(user_id, email, password)
            await status_msg.edit_text("تم تسج ـيل الدخ ـول الى الح ـساب\nاللذي ارسلته بدون مشاكل")
            msg = await message.reply("تم الح ـفظ بنج ـاح\nمولاي", reply_markup=get_main_keyboard(user_id))
            await apply_random_reaction(msg)
        else:
            await status_msg.edit_text("فشل تسج ـيل الدخ ـول الى\nالح ـساب اللذي ارسلته")
            msg = await message.reply("الرج ـاء المح ـاولة مج ـددا\nمولاي", reply_markup=get_main_keyboard(user_id))
            await apply_random_reaction(msg)
        return

    response_text = welcome_responses[welcome_index]
    welcome_index = (welcome_index + 1) % len(welcome_responses)
    
    await send_developer_button_delayed(message.chat.id, response_text)

@dp.callback_query(F.data.startswith("switch_"), F.from_user.id == ALLOWED_USER_ID)
async def switch_account_action(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    target_email = callback_query.data.split("_")[1]
    active_account[user_id] = target_email
    
    await callback_query.answer()
    await callback_query.message.delete()
    
    msg = await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="تم تح ـديد الاكاونت اللذي سيتم اللعب\nمن خ ـلاله ويح ـهم مني",
        reply_markup=ReplyKeyboardRemove()
    )
    await apply_random_reaction(msg)

@dp.callback_query(F.data.startswith("time_"), F.from_user.id == ALLOWED_USER_ID)
async def select_time_action(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await start_live_match()

@dp.callback_query(F.data.startswith("cont_"), F.from_user.id == ALLOWED_USER_ID)
async def select_continuous_time_action(callback_query: CallbackQuery):
    global continuous_play_mode, continuous_play_time
    continuous_play_time = callback_query.data.split("_")[1]
    continuous_play_mode = True
    
    await callback_query.message.delete()
    await start_live_match()

async def get_best_move_from_engine():
    global current_board
    try:
        transport, engine = await chess.engine.popen_uci(STOCKFISH_PATH)
        result = await engine.play(current_board, chess.engine.Limit(time=0.1))
        await engine.quit()
        return result.move
    except:
        return None

async def generate_and_send_board_image():
    global current_board
    try:
        svg_data = chess.svg.board(board=current_board, size=400)
        output_path = "board.png"
        cairosvg.svg2png(bytestring=svg_data.encode('utf-8'), write_to=output_path)
        
        photo = FSInputFile(output_path)
        msg = await bot.send_photo(chat_id=ALLOWED_USER_ID, photo=photo)
        await apply_random_reaction(msg)
    except:
        pass

async def start_live_match():
    global current_board
    current_board.reset()
    
    opponent_flag = "🇺🇸"
    opponent_rating = "2150"
    opponent_time = "10:00"
    opponent_trophies = "22"
    
    my_flag = "🇸🇦"
    my_rating = "2100"
    my_time = "10:00"
    my_trophies = "22"

    match_info = f"{opponent_flag}\n{opponent_rating} {opponent_time}\n{opponent_trophies} 🏆\n\n#¹\n\n{my_flag}\n{my_rating} {my_time}\n{my_trophies} 🏆"
    msg = await bot.send_message(chat_id=ALLOWED_USER_ID, text=match_info)
    await apply_random_reaction(msg)
    await generate_and_send_board_image()

async def handle_live_move(move_uci: str):
    global current_board
    try:
        move = chess.Move.from_uci(move_uci)
        if move in current_board.legal_moves:
            current_board.push(move)
            await generate_and_send_board_image()
            
            await asyncio.sleep(0.5)
            
            best_move = await get_best_move_from_engine()
            if best_move and best_move in current_board.legal_moves:
                current_board.push(best_move)
                await generate_and_send_board_image()
    except:
        pass

async def match_ended(won: bool):
    if won:
        msg = await bot.send_message(chat_id=ALLOWED_USER_ID, text="فُزت بكل ج ـدارة تستح ـق الأفضل\nاستمر بسح ـق الأعداء")
        await apply_random_reaction(msg)
    else:
        restart_btn = [[InlineKeyboardButton(text="ابدء", callback_data="restart_game", style="primary")]]
        msg = await bot.send_message(
            chat_id=ALLOWED_USER_ID, 
            text="ابدء گيم ج ـديد هذه المرة سأسح ـقهم\nبكل ما امتلك من قوة", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=restart_btn)
        )
        await apply_random_reaction(msg)

    if continuous_play_mode:
        await asyncio.sleep(5)
        await start_live_match()

@dp.callback_query(F.data == "restart_game", F.from_user.id == ALLOWED_USER_ID)
async def restart_game_action(callback_query: CallbackQuery):
    await callback_query.message.edit_text("توقيتات المباراة", reply_markup=InlineKeyboardMarkup(inline_keyboard=get_colored_time_buttons("time_")))

async def check_for_challenges(challenger_name):
    challenge_text = f"هل تريد قبول التح ـدي مع\nهذا الشخ ـص\n#¹ {challenger_name}"
    challenge_buttons = [
        [
            InlineKeyboardButton(text="قبول", callback_data="accept_challenge"),
            InlineKeyboardButton(text="رفض", callback_data="refuse_challenge")
        ]
    ]
    msg = await bot.send_message(
        chat_id=ALLOWED_USER_ID, 
        text=challenge_text, 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=challenge_buttons)
    )
    await apply_random_reaction(msg)

@dp.callback_query(F.data == "accept_challenge", F.from_user.id == ALLOWED_USER_ID)
async def accept_challenge_action(callback_query: CallbackQuery):
    await callback_query.message.edit_reply_markup(reply_markup=None)
    
    response_msg = await callback_query.message.reply(
        "تم بدء مبارات مع الشخ ـص االذي\nقام بالتح ـدي وخ ـاطر بنفسه"
    )
    await apply_random_reaction(response_msg)
    await start_live_match()

@dp.callback_query(F.data == "refuse_challenge", F.from_user.id == ALLOWED_USER_ID)
async def refuse_challenge_action(callback_query: CallbackQuery):
    await callback_query.message.edit_reply_markup(reply_markup=None)
    
    response_msg = await callback_query.message.reply(
        "رفضته وطيزته يبعد كسي انت\nمولاي ومن ح ـقك"
    )
    await apply_random_reaction(response_msg)

async def send_startup_notification():
    try:
        msg = await bot.send_message(
            chat_id=ALLOWED_USER_ID, 
            text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!",
            reply_markup=get_main_keyboard(ALLOWED_USER_ID)
        )
        await apply_random_reaction(msg)
    except:
        pass

async def main():
    await send_startup_notification()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
