import asyncio
import os
import re
import string
import random
from aiogram import Router, types, Bot
from yt_dlp import YoutubeDL

import STriNGs
import dATAbAse

yoT_router = Router()

def clean_filename_part(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9\s\-&]', '', text)
    cleaned = ' '.join(cleaned.split())
    result = []
    for char in cleaned:
        if char.isalpha():
            if char in 'ftanmjutFTANMJUT':
                result.append(char.upper())
            elif char in 'абиАБИ':
                result.append(char.upper())
            else:
                result.append(char.lower())
        else:
            result.append(char)
    return "".join(result).strip()

def generate_smart_filename(title: str) -> str:
    clean_title = clean_filename_part(title)
    if not clean_title:
        clean_title = "ANoNyMoUs"
    random_digits = "".join(random.choices(string.digits, k=9))
    return f"{clean_title} - {random_digits}"

async def process_yot_download(message: types.Message, search_query: str, bot: Bot, trigger_delayed_reaction, safe_send_food_emoji):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))
    
    start_text = f"بدءت بالعثور ع {search_query} انتظر بليز\nدادي"
    progress_msg = await message.reply(start_text)
    asyncio.create_task(trigger_delayed_reaction(bot, progress_msg.chat.id, progress_msg.message_id))
    
    loop = asyncio.get_running_loop()
    downloaded_file = None
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': 'downloads/%(title)s.%(ext)s',
    }
    
    try:
        ydl = YoutubeDL(ydl_opts)
        search_result = await loop.run_in_executor(
            None, 
            lambda: ydl.extract_info(f"ytsearch1:{search_query}", download=False)
        )
        
        if not search_result or 'entries' not in search_result or not search_result['entries']:
            raise Exception("No results found")
            
        entry = search_result['entries'][0]
        video_title = entry.get('title') or search_query
        custom_name = generate_smart_filename(video_title)
        
        entry_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'outtmpl': f'downloads/{custom_name}.%(ext)s'
        }
        
        entry_info = await loop.run_in_executor(
            None, 
            lambda: YoutubeDL(entry_opts).extract_info(entry['webpage_url'], download=True)
        )
        
        downloaded_file = YoutubeDL(entry_opts).prepare_filename(entry_info)
        
        try:
            await progress_msg.delete()
        except Exception:
            pass
            
        if os.path.exists(downloaded_file):
            file_input = types.FSInputFile(downloaded_file)
            sent_audio = await message.reply_audio(audio=file_input)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_audio.chat.id, sent_audio.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
        else:
            raise Exception("File not found after download")
            
    except Exception:
        try:
            await progress_msg.delete()
        except Exception:
            pass
        sent_err = await message.reply(STriNGs.ERROR_MESSAGE)
        asyncio.create_task(trigger_delayed_reaction(bot, sent_err.chat.id, sent_err.message_id))
        asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
    finally:
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
            except Exception:
                pass
