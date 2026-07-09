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

def apply_custom_case(text: str) -> str:
    result = []
    for char in text:
        if char.isalpha():
            if char in 'ftanmjutFTANMJUT':
                result.append(char.upper())
            elif char in 'абиАБИ':
                result.append(char.upper())
            else:
                result.append(char.lower())
        else:
            result.append(char)
    return "".join(result)

def clean_uploader_name(text: str) -> str:
    if not text:
        return "ANoNyMoUs"
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9\s\-&_]', '', text)
    cleaned = ' '.join(cleaned.split())
    if not cleaned:
        return "ANoNyMoUs"
    return apply_custom_case(cleaned).strip()

def clean_title_name(text: str) -> str:
    if not text:
        return "".join(random.choices(string.digits, k=9))
    
    if re.search(r'[\u0600-\u06FF]', text):
        return "".join(random.choices(string.digits, k=9))
        
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9\s\-&]', '', text)
    cleaned = cleaned.replace('_', '')
    cleaned = ' '.join(cleaned.split())
    
    if not cleaned:
        return "".join(random.choices(string.digits, k=9))
        
    return apply_custom_case(cleaned).strip()

def generate_yot_filename(uploader: str, title: str) -> str:
    clean_up = clean_uploader_name(uploader)
    clean_ti = clean_title_name(title)
    return f"{clean_up} - {clean_ti}"

async def process_yot_download(message: types.Message, search_query: str, bot: Bot, trigger_delayed_reaction, safe_send_food_emoji):
    asyncio.create_task(trigger_delayed_reaction(bot, message.chat.id, message.message_id))
    
    loop = asyncio.get_running_loop()
    
    ydl_opts_search = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        ydl_s = YoutubeDL(ydl_opts_search)
        search_result = await loop.run_in_executor(
            None, 
            lambda: ydl_s.extract_info(f"ytsearch1:{search_query}", download=False)
        )
        
        if not search_result or 'entries' not in search_result or not search_result['entries']:
            raise Exception("No results found")
            
        entry = search_result['entries'][0]
        video_id = entry.get('id')
        webpage_url = entry.get('webpage_url')
        
        if video_id:
            cache_key = f"yot_{video_id}"
            cached_ids = await dATAbAse.get_cached_file_ids(cache_key)
            if cached_ids and len(cached_ids) > 0:
                sent_audio = await message.reply_audio(audio=cached_ids[0])
                asyncio.create_task(trigger_delayed_reaction(bot, sent_audio.chat.id, sent_audio.message_id))
                asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
                return

        start_text = f"بدءت بالعثور ع {search_query} انتظر بليز دادي"
        progress_msg = await message.reply(start_text)
        asyncio.create_task(trigger_delayed_reaction(bot, progress_msg.chat.id, progress_msg.message_id))
        
        percent_msg = None
        last_reported_progress = 0
        
        def yot_hook(d):
            nonlocal last_reported_progress, percent_msg
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = int((downloaded / total) * 100)
                    if percent_msg is None:
                        percent_msg = asyncio.run_coroutine_threadsafe(
                            message.reply(f"{percent}%"),
                            loop
                        ).result()
                    elif percent >= last_reported_progress + 25:
                        last_reported_progress = (percent // 25) * 25
                        if last_reported_progress > 100:
                            last_reported_progress = 100
                        asyncio.run_coroutine_threadsafe(
                            percent_msg.edit_text(f"{last_reported_progress}%"),
                            loop
                        )

        uploader_name = entry.get('uploader') or entry.get('channel') or "ANoNyMoUs"
        video_title = entry.get('title') or ""
        custom_name = generate_yot_filename(uploader_name, video_title)
        
        entry_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [yot_hook],
            'outtmpl': f'downloads/{custom_name}.%(ext)s'
        }
        
        entry_info = await loop.run_in_executor(
            None, 
            lambda: YoutubeDL(entry_opts).extract_info(webpage_url, download=True)
        )
        
        downloaded_file = YoutubeDL(entry_opts).prepare_filename(entry_info)
        
        try:
            await progress_msg.delete()
        except Exception:
            pass
        try:
            if percent_msg:
                await percent_msg.delete()
        except Exception:
            pass
            
        if os.path.exists(downloaded_file):
            file_input = types.FSInputFile(downloaded_file)
            sent_audio = await message.reply_audio(audio=file_input)
            asyncio.create_task(trigger_delayed_reaction(bot, sent_audio.chat.id, sent_audio.message_id))
            asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
            
            if video_id and sent_audio.audio:
                await dATAbAse.save_cached_file_ids(f"yot_{video_id}", [sent_audio.audio.file_id])
        else:
            raise Exception("File missing")
            
    except Exception:
        try:
            await progress_msg.delete()
        except Exception:
            pass
        try:
            if percent_msg:
                await percent_msg.delete()
        except Exception:
            pass
        sent_err = await message.reply(STriNGs.ERROR_MESSAGE)
        asyncio.create_task(trigger_delayed_reaction(bot, sent_err.chat.id, sent_err.message_id))
        asyncio.create_task(safe_send_food_emoji(message.chat.id, message.message_id))
    finally:
        if 'downloaded_file' in locals() and downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
            except Exception:
                pass