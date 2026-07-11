import os
import io
import time
import random
import asyncio
from collections import deque
import aiohttp
import chess
import chess.svg
import cairosvg
from stockfish import Stockfish
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ButtonStyle
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

user_sessions = {}
recent_delays = deque(maxlen=5)

def get_human_delay():
    available_delays = [2.4, 4.8, 3.6, 6.3, 4.2, 8.4]
    while True:
        chosen_delay = random.choice(available_delays)
        if chosen_delay not in recent_delays:
            recent_delays.append(chosen_delay)
            return chosen_delay

def get_calibrated_move(board_fen, move_number):
    engine = Stockfish(path="stockfish")
    if move_number <= 10:
        engine.set_skill_level(20)
        engine.set_depth(15)
    else:
        dice = random.random()
        if dice < 0.75:
            engine.set_skill_level(18)
            engine.set_depth(14)
        elif dice < 0.95:
            engine.set_skill_level(15)
            engine.set_depth(12)
        else:
            engine.set_skill_level(10)
            engine.set_depth(10)
            
    engine.set_fen_position(board_fen)
    return engine.get_best_move()

async def send_dynamic_message(context, chat_id, full_text, reply_to_message_id=None, reply_markup=None, parse_mode=None):
    if not full_text:
        return None
        
    chunks = []
    index = 0
    take_12 = True
    
    while index < len(full_text):
        size = 12 if take_12 else 6
        chunks.append(full_text[index:index+size])
        index += size
        take_12 = not take_12

    current_text = chunks[0]
    message = await context.bot.send_message(
        chat_id=chat_id, 
        text=current_text, 
        reply_to_message_id=reply_to_message_id,
        parse_mode=parse_mode
    )
    
    for chunk in chunks[1:]:
        await asyncio.sleep(0.3)
        current_text += chunk
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message.message_id,
                text=current_text,
                parse_mode=parse_mode
            )
        except Exception:
            pass
            
    if reply_markup:
        await asyncio.sleep(0.3)
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message.message_id,
                reply_markup=reply_markup
            )
        except Exception:
            pass
            
    return message

async def send_board_image(context, chat_id, board):
    svg_data = chess.svg.board(board=board, size=400)
    png_output = io.BytesIO()
    cairosvg.svg2png(bytestring=svg_data.encode('utf-8'), write_to=png_output)
    png_output.seek(0)
    await context.bot.send_photo(chat_id=chat_id, photo=png_output)

async def handle_welcome_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id in user_sessions and user_sessions[user_id].get("active_game"):
        return

    if user_id in user_sessions:
        welcome_text = "لبدء مباراة اكتب اي امر من هذه الاوامر\nقيم / كيم / مباراة / مباراه / ماتش / بلاي / لعبة / لعبه"
        reply_markup = None
    else:
        welcome_text = "دز File بي كوكيز الاكاون مالتك علمود يستطيع ان pLAy البوت بدالك"
        keyboard = [[InlineKeyboardButton("المطور", url="tg://user?id=8467593882")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_dynamic_message(
        context=context, 
        chat_id=chat_id, 
        full_text=welcome_text, 
        reply_to_message_id=update.message.message_id, 
        reply_markup=reply_markup
    )

async def check_cookie_validity(cookies_str):
    url = "https://www.chess.com/callback/live/game/live-game-data"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookies_str
    }
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    return True
                return False
    except Exception:
        return False

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id in user_sessions and user_sessions[user_id].get("active_game"):
        return
        
    document = update.message.document
    file_name = document.file_name
    
    if file_name != "Cookie":
        return
        
    if user_id in user_sessions:
        duplicate_text = "الكوكيز مضاف من قبل شكد راح اضل اضيف بكوكيزك ابني"
        await send_dynamic_message(context, chat_id, duplicate_text, update.message.message_id)
        return
        
    file_bytes = await context.bot.get_file(document.file_id)
    custom_io = io.BytesIO()
    await file_bytes.download_to_memory(custom_io)
    cookie_content = custom_io.getvalue().decode('utf-8').strip()
    
    is_valid = await check_cookie_validity(cookie_content)
    
    if not is_valid:
        invalid_text = "كوكيز اكاونتك ليس صالح لا يستطيع البوت ان يبدأ المباريات"
        await send_dynamic_message(context, chat_id, invalid_text, update.message.message_id)
        return
        
    user_sessions[user_id] = {
        "cookies": cookie_content,
        "board": chess.Board(),
        "move_count": 1,
        "active_game": False,
        "win_rate": 84
    }
    
    success_text = "البوت اصبح يدعم اكاونتك ويستطيع بدء المباريات انطلق !"
    await send_dynamic_message(context, chat_id, success_text, update.message.message_id)

async def handle_win_rate_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id in user_sessions and user_sessions[user_id].get("active_game"):
        return
        
    text = update.message.text.strip()
    if not text.isdigit():
        return
        
    val = int(text)
    if 48 <= val <= 89:
        if user_id not in user_sessions:
            user_sessions[user_id] = {
                "cookies": "",
                "board": chess.Board(),
                "move_count": 1,
                "active_game": False,
                "win_rate": val
            }
        else:
            user_sessions[user_id]["win_rate"] = val
            
        rate_text = f"تغيرت نسبة الفوز المؤية الى {val}%\nابدأ مباراة الان ؟!"
        await send_dynamic_message(context, chat_id, rate_text, update.message.message_id)

async def show_time_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id in user_sessions and user_sessions[user_id].get("active_game"):
        return
        
    if user_id not in user_sessions or not user_sessions[user_id].get("cookies"):
        error_text = "اضف الكوكيز عبر ملف قم بتسميته Cookie ووضع كوكيز اكاونتك من موقع Chess.coM"
        await send_dynamic_message(context, chat_id, error_text, update.message.message_id)
        return

    keyboard = [
        [
            InlineKeyboardButton("1 دقيقة", callback_data="time_1m", style=ButtonStyle.DANGER),
            InlineKeyboardButton("1 + 1", callback_data="time_1_1", style=ButtonStyle.DANGER),
            InlineKeyboardButton("2 + 1", callback_data="time_2_1", style=ButtonStyle.DANGER)
        ],
        [
            InlineKeyboardButton("3 دقيقة", callback_data="time_3m", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("2 + 3", callback_data="time_2_3", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("5 دقيقة", callback_data="time_5m", style=ButtonStyle.PRIMARY)
        ],
        [
            InlineKeyboardButton("10 دقيقة", callback_data="time_10m", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("15 + 10", callback_data="time_15_10", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("30 دقيقة", callback_data="time_30m", style=ButtonStyle.SUCCESS)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_dynamic_message(
        context=context, 
        chat_id=chat_id, 
        full_text="توقيتات المباراة:", 
        reply_to_message_id=update.message.message_id, 
        reply_markup=reply_markup
    )

async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    await query.answer()
    await query.message.delete()
    
    if user_id in user_sessions:
        session = user_sessions[user_id]
        if session.get("active_game"):
            return
            
        session["board"] = chess.Board()
        session["move_count"] = 1
        session["active_game"] = True
        
        current_rate = session.get("win_rate", 84)
        
        start_text = f"بدأت مباراة مولاي يقوم البوت الان pLAyiNG\nاضمن لك الفوز بنسبة {current_rate}%\n\nالمستخدم: [{user_id}](tg://user?id={user_id})"
        
        keyboard = [[InlineKeyboardButton("اتمنى لك التوفيق", url=f"tg://user?id={user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_dynamic_message(
            context=context, 
            chat_id=chat_id, 
            full_text=start_text, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        await send_board_image(context, chat_id, session["board"])
        
        asyncio.create_task(process_game_loop(user_id, context, chat_id))

async def process_game_loop(user_id, context, chat_id):
    session = user_sessions.get(user_id)
    if not session:
        return
        
    board = session["board"]
    bot_color = chess.BLACK
    
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}) as http_session:
        headers = {"Cookie": session["cookies"]}
        
        while user_id in user_sessions and session["active_game"]:
            try:
                async with http_session.get("https://www.chess.com/callback/live/game/live-game-data", headers=headers) as response:
                    if response.status != 200:
                        await asyncio.sleep(2)
                        continue
                    
                    data = await response.json()
                    game_data = data.get("game", {})
                    game_moves = game_data.get("moves", "")
                    
                    parsed_moves = game_moves.split()
                    total_moves = len(parsed_moves)
                    
                    if total_moves == 0 and game_data.get("whiteUrl", "").lower().endswith(str(user_id)):
                        bot_color = chess.WHITE
                    
                    if (board.turn == chess.WHITE and total_moves % 2 == 0) or (board.turn == chess.BLACK and total_moves % 2 != 0):
                        if total_moves > 0:
                            last_move = parsed_moves[-1]
                            try:
                                parsed_move = board.parse_san(last_move)
                                if parsed_move in board.legal_moves:
                                    board.push(parsed_move)
                                    session["move_count"] += 1
                                    await send_board_image(context, chat_id, board)
                            except ValueError:
                                pass
                        
                        if board.is_game_over():
                            session["active_game"] = False
                            res = board.result()
                            if (res == "1-0" and bot_color == chess.WHITE) or (res == "0-1" and bot_color == chess.BLACK):
                                await send_dynamic_message(context, chat_id, "فُزت")
                            elif (res == "0-1" and bot_color == chess.WHITE) or (res == "1-0" and bot_color == chess.BLACK):
                                await send_dynamic_message(context, chat_id, "هزمني")
                            break
                            
                        best_move = get_calibrated_move(board.fen(), session["move_count"])
                        
                        delay = get_human_delay()
                        await asyncio.sleep(delay)
                        
                        move_data = {"move": best_move, "gameId": game_data.get("id")}
                        async with http_session.post("https://www.chess.com/callback/live/game/make-move", headers=headers, json=move_data) as move_resp:
                            if move_resp.status == 200:
                                board.push(chess.Move.from_uci(best_move))
                                session["move_count"] += 1
                                await send_board_image(context, chat_id, board)
                                
                        if board.is_game_over():
                            session["active_game"] = False
                            res = board.result()
                            if (res == "1-0" and bot_color == chess.WHITE) or (res == "0-1" and bot_color == chess.BLACK):
                                await send_dynamic_message(context, chat_id, "فُزت")
                            elif (res == "0-1" and bot_color == chess.WHITE) or (res == "1-0" and bot_color == chess.BLACK):
                                await send_dynamic_message(context, chat_id, "هزمني")
                            break
                                
                await asyncio.sleep(1)
            except Exception:
                await asyncio.sleep(1)

def main():
    if not TOKEN:
        return
        
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", handle_welcome_logic))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    match_filter = filters.Regex(r'^(قيم|كيم|مباراة|مباراه|ماتش|بلاي|لعبة|لعبه)$')
    app.add_handler(MessageHandler(match_filter, show_time_options))
    
    app.add_handler(MessageHandler(filters.Regex(r'^\d+$'), handle_win_rate_change))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_welcome_logic))
    app.add_handler(CallbackQueryHandler(handle_time_selection, pattern="^time_"))
    
    app.run_polling()

if __name__ == "__main__":
    main()
