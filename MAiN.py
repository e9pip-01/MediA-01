import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

import random
import string
import yt_dlp
import re
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup
from yoT import download_youtube_audio
import eDT
import cAshe
import bUTToNs

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

user_queues = {}
active_downloads = 0
download_lock = asyncio.Lock()

def is_arabic(text):
    return any('\u0600' <= char <= '\u06FF' for char in text)

def clean_name(name):
    allowed = "-&"
    cleaned = ""
    for char in name:
        if char.isalnum() or char in allowed or char.isspace():
            cleaned += char
    return cleaned.strip()

def format_uploader(name):
    if is_arabic(name):
        return ""
    name = name.lower()
    chars_to_upper = "aftgjunmаби"
    new_name = ""
    for char in name:
        if char in chars_to_upper:
            new_name += char.upper()
        else:
            new_name += char
    return re.sub(r'[^a-zA-Zа-яА-Я& ]', '', new_name).strip()

async def queue_worker(user_id):
    global active_downloads
    queue = user_queues[user_id]
    while not queue.empty():
        async with download_lock:
            if active_downloads >= 3:
                await asyncio.sleep(0.5)
                continue
            active_downloads += 1
            
        task = await queue.get()
        try:
            await task()
        except:
            pass
        finally:
            async with download_lock:
                active_downloads -= 1
            queue.task_done()

@dp.message(F.chat.type != "private")
async def block_groups(message: types.Message):
    return

@dp.message(F.text == "ادت")
async def edt_cmd(message: types.Message):
    await eDT.handle_edt_command(message)

@dp.callback_query()
async def cb_handler(callback: types.CallbackQuery):
    await eDT.handle_edt_callback(callback)

@dp.message(F.text.startswith("يوت ") & (F.text.len() > 4))
async def youtube_handler(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue(maxsize=6)
        
    if user_queues[user_id].full():
        return
        
    async def task():
        await download_youtube_audio(message)
        
    await user_queues[user_id].put(task)
    if user_queues[user_id].qsize() == 1:
        asyncio.create_task(queue_worker(user_id))

@dp.message(F.text.startswith("https://") | F.text.startswith("http://"))
async def link_download_handler(message: types.Message):
    user_id = message.from_user.id
    url = message.text.strip()
    
    cached_file_id = await cAshe.get_cached_file(url)
    btn_pub = eDT.get_public_button()
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_pub]])
    
    if cached_file_id:
        await message.reply_document(cached_file_id, reply_markup=kb)
        await message.reply("يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك", reply_markup=kb)
        return

    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue(maxsize=6)
        
    if user_queues[user_id].full():
        return

    async def task():
        status_msg = await message.reply(f"بدءت بالعثور ع {url} انتظر بليز\nدادي")
        progress_msg = await message.reply("0%")
        asyncio.create_task(bUTToNs.trigger_reaction(message))

        last_percent = -1

        def progress_hook(d):
            nonlocal last_percent
            if d['status'] == 'downloading':
                p = d.get('_percent_str', '0%').strip().replace('%', '')
                try:
                    val = int(float(p))
                    if val % 25 == 0 and val != last_percent:
                        last_percent = val
                        asyncio.run_coroutine_threadsafe(progress_msg.edit_text(f"{val}%"), bot.session.loop)
                except: pass

        opts = {
            'format': 'best',
            'progress_hooks': [progress_hook],
            'quiet': True,
            'outtmpl': '%(title)s.%(ext)s'
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if 'entries' in info:
                    entries = info['entries']
                    file_batches = []
                    current_batch = []
                    
                    for entry in entries:
                        if entry is None: continue
                        full_path = ydl.prepare_filename(entry)
                        if not os.path.exists(full_path):
                            actual_ext = entry.get('ext', '')
                            base_path = os.path.splitext(full_path)[0]
                            full_path = f"{base_path}.{actual_ext}"
                            
                        if os.path.exists(full_path):
                            uploader = clean_name(entry.get('uploader', 'unknown'))
                            rnd = ''.join(random.choices(string.digits, k=9))
                            detected_ext = os.path.splitext(full_path)[1].lstrip('.')
                            
                            if is_arabic(uploader):
                                filename = f"{rnd}.{detected_ext}"
                            else:
                                formatted_up = format_uploader(uploader)
                                filename = f"{formatted_up} - {rnd}.{detected_ext}"
                                
                            current_batch.append((full_path, filename))
                            if len(current_batch) == 8:
                                file_batches.append(current_batch)
                                current_batch = []
                    if current_batch:
                        file_batches.append(current_batch)
                        
                    await bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
                    await bot.delete_message(chat_id=message.chat.id, message_id=progress_msg.message_id)
                    
                    for b_idx, batch in enumerate(file_batches):
                        media_group = []
                        for full_path, filename in batch:
                            with open(full_path, 'rb') as f:
                                file_data = f.read()
                            media_group.append(types.InputMediaDocument(media=BufferedInputFile(file_data, filename=filename)))
                        
                        await message.reply_media_group(media=media_group)
                            
                        for full_path, _ in batch:
                            cAshe.clear_system_file(full_path)
                    await message.reply("يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك", reply_markup=kb)
                else:
                    full_path = ydl.prepare_filename(info)
                    if not os.path.exists(full_path):
                        actual_ext = info.get('ext', '')
                        base_path = os.path.splitext(full_path)[0]
                        full_path = f"{base_path}.{actual_ext}"
                        
                    uploader = clean_name(info.get('uploader', 'unknown'))
                    rnd = ''.join(random.choices(string.digits, k=9))
                    detected_ext = os.path.splitext(full_path)[1].lstrip('.')
                    
                    if is_arabic(uploader):
                        filename = f"{rnd}.{detected_ext}"
                    else:
                        formatted_up = format_uploader(uploader)
                        filename = f"{formatted_up} - {rnd}.{detected_ext}"
                    
                    with open(full_path, 'rb') as f:
                        file_data = f.read()
                    
                    await bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
                    
                    sent_doc = await bot.edit_message_media(
                        chat_id=message.chat.id,
                        message_id=progress_msg.message_id,
                        media=types.InputMediaDocument(media=BufferedInputFile(file_data, filename=filename)),
                        reply_markup=kb
                    )
                    await message.reply("يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك", reply_markup=kb)
                    
                    if sent_doc.document:
                        await cAshe.set_file_cache(url, sent_doc.document.file_id)
                        
                    cAshe.clear_system_file(full_path)
        except Exception:
            try:
                await progress_msg.edit_text("الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي")
            except:
                pass

    await user_queues[user_id].put(task)
    if user_queues[user_id].qsize() == 1:
        asyncio.create_task(queue_worker(user_id))

@dp.message()
async def handle_chat_and_inputs(message: types.Message):
    if message.text:
        is_edt_process = await eDT.process_edt_inputs(message)
        if is_edt_process:
            return
            
    await bUTToNs.handle_default_response(message)

async def main():
    await cAshe.init_db()
    asyncio.create_task(bUTToNs.send_startup_messages(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
