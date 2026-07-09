import os
import re
import time
import random
import string
import asyncio
from yt_dlp import YoutubeDL
from aiogram import types, Bot

import STriNGs
import dATAbAse

def cleanup_stale_files():
    downloads_dir = 'downloads'
    if not os.path.exists(downloads_dir):
        return
    now = time.time()
    for filename in os.listdir(downloads_dir):
        file_path = os.path.join(downloads_dir, filename)
        if os.path.isfile(file_path):
            if now - os.path.getmtime(file_path) > 3600:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

def clean_filename_part(text: str) -> str:
    if not text:
        return ""
    
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9\s\-&_]', '', text)
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

def generate_smart_filename(uploader: str) -> str:
    clean_uploader = clean_filename_part(uploader)
    if not clean_uploader:
        clean_uploader = "ANoNyMoUs"
        
    random_digits = "".join(random.choices(string.digits, k=9))
    return f"{clean_uploader} - {random_digits}"

async def process_download_task(message: types.Message, url_text: str, bot: Bot, animate_func, trigger_reaction_func):
    asyncio.create_task(trigger_reaction_func(bot, message.chat.id, message.message_id))
    
    cached_ids = await dATAbAse.get_cached_file_ids(url_text)
    if cached_ids:
        try:
            chunks = [cached_ids[i:i + 8] for i in range(0, len(cached_ids), 8)]
            for chunk in chunks:
                media_group = []
                for fid in chunk:
                    media_group.append(types.InputMediaDocument(media=fid))
                
                if len(media_group) == 1:
                    sent = await message.reply_document(media_group[0].media)
                    asyncio.create_task(trigger_reaction_func(bot, sent.chat.id, sent.message_id))
                else:
                    sent_group = await message.reply_media_group(media=media_group)
                    if sent_group:
                        asyncio.create_task(trigger_reaction_func(bot, sent_group[0].chat.id, sent_group[0].message_id))

            await animate_func(message, STriNGs.SUCCESS_MESSAGE)
            return
        except Exception:
            pass

    cleanup_stale_files()
    
    progress_text_msg = await animate_func(message, STriNGs.PROGRESS_START)
    progress_percent_msg = await bot.send_message(chat_id=message.chat.id, text="%")
    
    last_reported_progress = 0
    downloaded_files = []
    
    loop = asyncio.get_running_loop()

    def ytdl_hook(d):
        nonlocal last_reported_progress
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                if percent > 10 and percent >= last_reported_progress + 20:
                    last_reported_progress = (percent // 20) * 20
                    asyncio.run_coroutine_threadsafe(
                        progress_percent_msg.edit_text(STriNGs.PROGRESS_TEMPLATE.format(percent=last_reported_progress)),
                        loop
                    )

    ydl_opts = {
        'format': 'best',
        'progress_hooks': [ytdl_hook],
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False
    }
    
    try:
        ydl = YoutubeDL(ydl_opts)
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url_text, download=False))
        
        uploader = info.get('uploader') or info.get('channel') or "ANoNyMoUs"
        
        entries = []
        if 'entries' in info and info['entries']:
            entries = [e for e in info['entries'] if e]
        else:
            entries = [info]
            
        for entry in entries:
            custom_name = generate_smart_filename(uploader)
            entry_opts = {
                'format': 'best',
                'outtmpl': f'downloads/{custom_name}.%(ext)s',
                'quiet': True,
                'no_warnings': True
            }
            entry_info = await loop.run_in_executor(None, lambda: YoutubeDL(entry_opts).extract_info(entry.get('webpage_url') or url_text, download=True))
            filename = YoutubeDL(entry_opts).prepare_filename(entry_info)
            if os.path.exists(filename):
                downloaded_files.append(filename)

        try:
            await progress_text_msg.delete()
            await progress_percent_msg.delete()
        except Exception:
            pass
        
        if downloaded_files:
            chunks = [downloaded_files[i:i + 8] for i in range(0, len(downloaded_files), 8)]
            uploaded_file_ids = []
            
            for chunk in chunks:
                media_group = []
                for filepath in chunk:
                    file_input = types.FSInputFile(filepath)
                    media_group.append(types.InputMediaDocument(media=file_input))
                
                if len(media_group) == 1:
                    sent_doc = await message.reply_document(media_group[0].media)
                    uploaded_file_ids.append(sent_doc.document.file_id)
                    asyncio.create_task(trigger_reaction_func(bot, sent_doc.chat.id, sent_doc.message_id))
                else:
                    sent_group = await message.reply_media_group(media=media_group)
                    if sent_group:
                        asyncio.create_task(trigger_reaction_func(bot, sent_group[0].chat.id, sent_group[0].message_id))
                    for sent_msg in sent_group:
                        if sent_msg.document:
                            uploaded_file_ids.append(sent_msg.document.file_id)
            
            if uploaded_file_ids:
                await dATAbAse.save_cached_file_ids(url_text, uploaded_file_ids)
                
            await animate_func(message, STriNGs.SUCCESS_MESSAGE)
        else:
            await animate_func(message, STriNGs.FILE_NOT_FOUND)
            
    except Exception:
        try:
            await progress_text_msg.delete()
            await progress_percent_msg.delete()
        except Exception:
            pass
        await animate_func(message, STriNGs.ERROR_MESSAGE)
    finally:
        for filepath in downloaded_files:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
