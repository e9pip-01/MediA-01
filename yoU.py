import os, asyncio, tempfile, glob
from collections import defaultdict, deque
import yt_dlp
from yt_dlp.utils import UnsupportedError
from aiogram import Bot, Dispatcher
from aiogram.types import Message, FSInputFile, ReactionTypeEmoji

TOKEN = os.getenv("BOT_TOKEN")
MAX = 456 * 1024 * 1024
active, queues = defaultdict(int), defaultdict(deque)
locks = defaultdict(asyncio.Lock)
reply_i, react_i, time_i = defaultdict(int), defaultdict(int), defaultdict(int)

REPLIES = [
"اهلين وياك بوت تنزيل وسائط تريد اشتغل\nدز رابط وتدلل",
"مو ناوي تدلعني مثل البوتات\nترى ازعل منك اصيح المولاي يغصص بلاعيمك",
"راح اكلك شعر يهبل كتبته بماي كسي\nراح اونسك بس اسمع
",
"من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
"انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح",
]

REACTIONS = ["🥰", "🤣", "🍓", "😭", "😘"]
TIMES = [2.4, 4.2, 4.8, 3.6, 3.2, 2.3]

BAD = "¹# - الرابط غير مدعوم او الموقع مو مدعوم\nامم دز رابط غير هذا"
ERR = "¹# - ربما الموقع غير مدعوم او ليس ضمن\nقدرات البوت"

def sz(f):
return f.get("filesize") or f.get("filesize_approx") or 0

def choose(info):
fs = info.get("formats", [])
v = [f for f in fs if f.get("vcodec") != "none" and sz(f)]
both = [f for f in v if f.get("acodec") != "none" and sz(f) <= MAX]
if both:
return max(both, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))

vo = [f for f in v if f.get("acodec") == "none"]  
au = [f for f in fs if f.get("vcodec") == "none" and f.get("acodec") != "none" and sz(f)]  
pairs = [(v, a) for v in vo for a in au if sz(v) + sz(a) <= MAX]  
return max(  
    pairs,  
    key=lambda p: (p[0].get("height") or 0, p[0].get("tbr") or 0)  
) if pairs else None

async def react(m):
uid = m.from_user.id
r = REACTIONS[react_i[uid] % len(REACTIONS)]
t = TIMES[time_i[uid] % len(TIMES)]
react_i[uid] += 1
time_i[uid] += 1
await asyncio.sleep(t)
try:
await m.react([ReactionTypeEmoji(emoji=r)])
except Exception:
pass

async def auto_reply(m):
uid = m.from_user.id
text = REPLIES[reply_i[uid] % len(REPLIES)]
reply_i[uid] += 1
r = await m.reply(text)
asyncio.create_task(react(r))

async def work(m, url):
uid = m.from_user.id
try:
def extract():
with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as y:
return y.extract_info(url, download=False)

try:  
        info = await asyncio.to_thread(extract)  
    except UnsupportedError:  
        await m.reply(BAD)  
        return  

    choice = choose(info)  
    if not choice:  
        await m.reply(ERR)  
        return  

    with tempfile.TemporaryDirectory() as d:  
        fmt = (  
            f"{choice[0]['format_id']}+{choice[1]['format_id']}"  
            if isinstance(choice, tuple)  
            else choice["format_id"]  
        )  
        out = f"{d}/%(uploader)s - %(title)s.%(ext)s"  

        def download():  
            with yt_dlp.YoutubeDL({  
                "quiet": True,  
                "no_warnings": True,  
                "format": fmt,  
                "outtmpl": out,  
            }) as y:  
                y.download([url])  

        await asyncio.to_thread(download)  
        files = glob.glob(f"{d}/*")  

        if not files:  
            await m.reply(ERR)  
            return  

        sent = await m.reply_document(FSInputFile(files[0]))  
        asyncio.create_task(react(sent))  

except Exception:  
    await m.reply(ERR)  

finally:  
    async with locks[uid]:  
        active[uid] -= 1  
        if queues[uid]:  
            msg, url = queues[uid].popleft()  
            active[uid] += 1  
            asyncio.create_task(work(msg, url))

async def handle(m: Message):
if not m.text:
return

if m.text.startswith(("http://", "https://")):  
    uid = m.from_user.id  
    asyncio.create_task(react(m))  

    async with locks[uid]:  
        if active[uid] >= 3:  
            if len(queues[uid]) >= 2:  
                return  
            queues[uid].append((m, m.text))  
            return  
        active[uid] += 1  

    asyncio.create_task(work(m, m.text))  
else:  
    asyncio.create_task(react(m))  
    await auto_reply(m)

async def main():
bot = Bot(TOKEN)
dp = Dispatcher()
dp.message.register(handle)
await dp.start_polling(bot)

if name == "main":
asyncio.run(main())