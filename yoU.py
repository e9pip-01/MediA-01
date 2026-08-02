import os
import asyncio
import logging
import ffmpeg
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_reply_state = {}
alternating_responses = [
    "هلا بيك يا بعد حيي.. أرسل لي فيديو عشان أحوله لك دائرة 🌹",
    "يا هلي وناسي، هذا مو فيديو! أرسل لي فيديو وخلنا نونسك ✨",
    "منورني والله بس احتاج مقطع فيديو عشان أقدر أخدمك صح 🎬"
]

def process_video_ffmpeg(input_path, output_path):
    (
        ffmpeg
        .input(input_path)
        .filter('crop', 'ih', 'ih')
        .filter('scale', 384, 384)
        .output(
            output_path,
            vcodec='libx264',
            acodec='aac',
            r=30
        )
        .overwrite_output()
        .run(quiet=True)
    )

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer("أهلاً بك! أرسلي لي أي مقطع فيديو وسأقوم بتحويله إلى رسالة مرئية دائرية فوراً.")

@dp.message(F.video | F.animation | F.document)
async def video_file_handler(message: Message):
    file = message.video or message.animation or message.document
    
    if not file.mime_type or not file.mime_type.startswith("video/"):
        await handle_alternating_reply(message)
        return

    status_msg = await message.answer("جاري تحميل الفيديو وتحويله إلى دائرة بأقصى سرعة... ⏳")

    timestamp = message.message_id
    raw_path = f"raw_{timestamp}.mp4"
    output_path = f"output_{timestamp}.mp4"

    try:
        tg_file = await bot.get_file(file.file_id)
        
        async with httpx.AsyncClient(http2=True) as client:
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{tg_file.file_path}"
            response = await client.get(file_url)
            with open(raw_path, "wb") as f:
                f.write(response.content)

        await asyncio.to_thread(process_video_ffmpeg, raw_path, output_path)

        video_note = FSInputFile(output_path)
        await bot.send_video_note(chat_id=message.chat.id, video_note=video_note)
        await bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)

    except Exception as e:
        logging.error(f"Error processing video: {e}")
        await message.answer("حدث خطأ أثناء معالجة الفيديو، تأكدي من الملف وحاولي مجدداً.")

    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)
        if os.path.exists(output_path):
            os.remove(output_path)

@dp.message()
async def non_video_handler(message: Message):
    if message.text and message.text.startswith('/'):
        return
    await handle_alternating_reply(message)

async def handle_alternating_reply(message: Message):
    user_id = message.from_user.id
    current_index = user_reply_state.get(user_id, 0)
    
    await message.answer(alternating_responses[current_index])
    user_reply_state[user_id] = (current_index + 1) % len(alternating_responses)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
