import asyncio
import os
import re
import unicodedata
from pathlib import Path

import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

TOKEN = os.environ["BOT_TOKEN"]

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_ACTIVE = 3
MAX_QUEUE = 3

users = {}
users_lock = asyncio.Lock()

EN_UPPER = set("ATGUFNJML")
RU_UPPER = set("АИБ")


def is_telegram_url(url):
    match = re.match(r"^https?://([^/]+)", url.lower())
    if not match:
        return False

    domain = match.group(1).split(":")[0]

    return (
        domain == "t.me"
        or domain.endswith(".t.me")
        or domain == "telegram.me"
        or domain.endswith(".telegram.me")
        or domain == "telegram.dog"
        or domain.endswith(".telegram.dog")
    )


def clean_publisher(name):
    name = unicodedata.normalize("NFC", name or "")
    result = []

    for char in name:
        if char.isascii() and char.isalpha():
            result.append(
                char.upper()
                if char.upper() in EN_UPPER
                else char.lower()
            )

        elif "\u0400" <= char <= "\u04FF":
            result.append(
                char.upper()
                if char.upper() in RU_UPPER
                else char.lower()
            )

        elif char.isdigit() or char in "_ ":
            result.append(char)

    return "".join(result).strip()


def clean_title(name):
    return re.sub(
        r'[<>:"/\\|?*\x00-\x1F]',
        "",
        name or "",
    )


def make_filename(publisher, title, extension):
    return (
        f"{clean_publisher(publisher)} - "
        f"{clean_title(title)}.{extension}"
    )


def get_user_state(user_id):
    if user_id not in users:
        users[user_id] = {
            "mode": "normal",
            "queue": asyncio.Queue(maxsize=MAX_QUEUE),
            "running": 0,
            "tasks": set(),
        }

    return users[user_id]


def mode_keyboard(user_id):
    mode = get_user_state(user_id)["mode"]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="صوت",
                    callback_data="mode_audio",
                    style=(
                        "success"
                        if mode == "audio"
                        else "danger"
                    ),
                ),
                InlineKeyboardButton(
                    text="ستيكر",
                    callback_data="mode_sticker",
                    style=(
                        "success"
                        if mode == "sticker"
                        else "danger"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="الافتراضي",
                    callback_data="mode_normal",
                    style=(
                        "success"
                        if mode == "normal"
                        else "danger"
                    ),
                ),
            ],
        ]
    )


def download(url, folder, mode):
    if mode == "audio":
        fmt = "bestaudio/best"

    elif mode == "sticker":
        fmt = "bestvideo/best"

    else:
        fmt = "bestvideo+bestaudio/best"

    options = {
        "format": fmt,
        "outtmpl": str(folder / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            url,
            download=True,
        )

        path = Path(
            ydl.prepare_filename(info)
        )

        if not path.exists():
            files = list(folder.glob("*"))

            if not files:
                raise FileNotFoundError(
                    "Download failed"
                )

            path = max(
                files,
                key=lambda f: f.stat().st_mtime,
            )

        return path, info


async def convert_to_sticker(path):
    output = path.with_name(
        f"{path.stem}_sticker.mp4"
    )

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-an",
        "-movflags",
        "+faststart",
        str(output),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    code = await process.wait()

    if code != 0 or not output.exists():
        raise RuntimeError(
            "FFmpeg conversion failed"
        )

    return output


async def send_audio_file(
    bot,
    user_id,
    path,
    filename,
):
    await bot.send_audio(
        chat_id=user_id,
        audio=FSInputFile(
            path,
            filename=filename,
        ),
    )


async def send_animation_file(
    bot,
    user_id,
    path,
):
    await bot.send_animation(
        chat_id=user_id,
        animation=FSInputFile(
            path,
            filename=path.name,
        ),
    )


async def process(
    user_id,
    url,
    bot,
    mode,
):
    folder = DOWNLOAD_DIR / str(user_id)
    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = None
    final_path = None
    sticker_path = None

    try:
        path, info = await asyncio.to_thread(
            download,
            url,
            folder,
            mode,
        )

        publisher = (
            info.get("uploader")
            or info.get("channel")
            or "unknown"
        )

        title = (
            info.get("title")
            or path.stem
        )

        extension = (
            path.suffix
            .lstrip(".")
            .lower()
        )

        filename = make_filename(
            publisher,
            title,
            extension,
        )

        final_path = path.with_name(filename)

        if path != final_path:
            if final_path.exists():
                final_path.unlink()

            path.rename(final_path)

        if mode == "audio":
            await send_audio_file(
                bot,
                user_id,
                final_path,
                filename,
            )

        elif mode == "sticker":
            sticker_path = (
                await convert_to_sticker(
                    final_path
                )
            )

            await send_animation_file(
                bot,
                user_id,
                sticker_path,
            )

        else:
            await bot.send_document(
                chat_id=user_id,
                document=FSInputFile(
                    final_path,
                    filename=filename,
                ),
            )

    except Exception:
        pass

    finally:
        for file in (
            sticker_path,
            final_path,
            path,
        ):
            if file and file.exists():
                try:
                    file.unlink()
                except Exception:
                    pass


async def cleanup_task(user_id, task):
    async with users_lock:
        state = users.get(user_id)

        if state:
            state["tasks"].discard(task)


async def run_download(
    user_id,
    url,
    bot,
    mode,
):
    try:
        await process(
            user_id,
            url,
            bot,
            mode,
        )

    finally:
        async with users_lock:
            state = users.get(user_id)

            if not state:
                return

            state["running"] -= 1

            if not state["queue"].empty():
                next_url, next_mode = (
                    await state["queue"].get()
                )

                state["running"] += 1

                task = asyncio.create_task(
                    run_download(
                        user_id,
                        next_url,
                        bot,
                        next_mode,
                    )
                )

                state["tasks"].add(task)

                task.add_done_callback(
                    lambda task,
                    uid=user_id:
                    asyncio.create_task(
                        cleanup_task(
                            uid,
                            task,
                        )
                    )
                )

            elif state["running"] <= 0:
                users.pop(
                    user_id,
                    None,
                )


async def add_download(
    user_id,
    url,
    bot,
):
    async with users_lock:
        state = get_user_state(user_id)

        total = (
            state["running"]
            + state["queue"].qsize()
        )

        if total >= MAX_ACTIVE + MAX_QUEUE:
            return

        mode = state["mode"]

        if state["running"] < MAX_ACTIVE:
            state["running"] += 1

            task = asyncio.create_task(
                run_download(
                    user_id,
                    url,
                    bot,
                    mode,
                )
            )

            state["tasks"].add(task)

            task.add_done_callback(
                lambda task,
                uid=user_id:
                asyncio.create_task(
                    cleanup_task(
                        uid,
                        task,
                    )
                )
            )

        else:
            await state["queue"].put(
                (url, mode)
            )


bot = Bot(TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message):
    pass


@dp.message(F.text == "ادت")
async def download_settings(message):
    user_id = message.from_user.id

    async with users_lock:
        get_user_state(user_id)

    await message.answer(
        "إعدادات التحميل",
        reply_markup=mode_keyboard(user_id),
    )


@dp.callback_query(F.data == "mode_audio")
async def select_audio(callback: CallbackQuery):
    user_id = callback.from_user.id

    async with users_lock:
        state = get_user_state(user_id)

        if state["mode"] == "audio":
            state["mode"] = "normal"
        else:
            state["mode"] = "audio"

        keyboard = mode_keyboard(user_id)

    await callback.message.edit_reply_markup(
        reply_markup=keyboard
    )

    await callback.answer()


@dp.callback_query(F.data == "mode_sticker")
async def select_sticker(callback: CallbackQuery):
    user_id = callback.from_user.id

    async with users_lock:
        state = get_user_state(user_id)

        if state["mode"] == "sticker":
            state["mode"] = "normal"
        else:
            state["mode"] = "sticker"

        keyboard = mode_keyboard(user_id)

    await callback.message.edit_reply_markup(
        reply_markup=keyboard
    )

    await callback.answer()


@dp.callback_query(F.data == "mode_normal")
async def select_normal(callback: CallbackQuery):
    user_id = callback.from_user.id

    async with users_lock:
        state = get_user_state(user_id)

        if state["mode"] == "normal":
            await callback.answer(
                "لا يمكنك تعطيل الوضع الافتراضي\n"
                "تستطيع تبديل الوضع وليس تعطيل كل الاوضاع",
                show_alert=True,
            )
            return

        state["mode"] = "normal"
        keyboard = mode_keyboard(user_id)

    await callback.message.edit_reply_markup(
        reply_markup=keyboard
    )

    await callback.answer()


@dp.message(F.text)
async def link_handler(message):
    url = message.text.strip()

    if message.text == "ادت":
        return

    if not re.match(r"^https?://", url):
        return

    if is_telegram_url(url):
        return

    await add_download(
        message.from_user.id,
        url,
        bot,
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())