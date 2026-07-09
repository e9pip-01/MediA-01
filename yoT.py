import random
import string
import yt_dlp
import re
import os
from aiogram import types
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup
import cAshe
import eDT

def is_arabic(text):
    return any('\u0600' <= char <= '\u06FF' for char in text)

def clean_name(name):
    allowed = "-&"
    cleaned = ""
    for char in name:
        if char.isalnum() or char in allowed or char.isspace():
            cleaned += char
    return cleaned.strip()

def format_title(name):
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

async def download_youtube_audio(message: types.Message):
    query = message.text[4:].strip()
    status_msg = await message.reply(f"بدءت بالعثور ع {query} انتظر بليز\nدادي")
    
    opts = {
        'format': 'bestaudio',
        'quiet': True,
        'default_search': 'ytsearch1',
        'outtmpl': '%(title)s.%(ext)s'
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            extract_info = ydl.extract_info(query, download=False)
            if 'entries' in extract_info:
                video_info = extract_info['entries'][0]
            else:
                video_info = extract_info
                
            video_id = video_info.get('id')
            cached_id = await cAshe.get_yt_cache(video_id)
            
            btn_pub = eDT.get_public_button()
            kb = InlineKeyboardMarkup(inline_keyboard=[[btn_pub]])
            
            if cached_id:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
                await message.reply_audio(cached_id, reply_markup=kb)
                return

            info = ydl.extract_info(query, download=True)
            if 'entries' in info:
                info = info['entries'][0]
                
            full_path = ydl.prepare_filename(info)
            title = clean_name(info.get('title', 'audio'))
            rnd = ''.join(random.choices(string.digits, k=9))
            
            raw_ext = info.get('ext', 'mp3')
            
            if is_arabic(title):
                filename = f"{rnd}.{raw_ext}"
            else:
                formatted_title = format_title(title)
                filename = f"{formatted_title} - {rnd}.{raw_ext}"
                
        with open(full_path, 'rb') as f:
            file_data = f.read()
            
        await message.bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
        sent_audio = await message.reply_audio(BufferedInputFile(file_data, filename=filename), reply_markup=kb)
        
        if video_id and sent_audio.audio:
            await cAshe.set_yt_cache(video_id, sent_audio.audio.file_id)
            
        cAshe.clear_system_file(full_path)
    except Exception:
        await status_msg.edit_text("الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي")
