import random
from aiogram import types

DEVELOPER_ID = "8597653867"
SUPPORT_ID = "8467593882"

DEFAULT_SUBSCRIBE_LINK = "tg://user?id=8597653867"
DEFAULT_BUTTON_TEXT = "تواصل مع المطور"
DEFAULT_BUTTON_STYLE = "primary"

SUPPORT_LINK = "tg://user?id=8467593882"
BTN_SUPPORT = "ابلاغ الدعم"
SUPPORT_BUTTON_STYLE = "destructive"

PROGRESS_START = "انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا"
PROGRESS_TEMPLATE = "انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا {percent}%"
ERROR_MESSAGE = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
FILE_NOT_FOUND = ERROR_MESSAGE

SUCCESS_MESSAGE = "يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك"
STARTUP_MESSAGE = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
QUEUE_FULL_MESSAGE = "سته عمليات داشتغل عليهم وبعدك تريد\nلعد شكد ملعوب بعرضك"

REACTION_EMOJIS = ["🥰", "😡", "😭", "🍓", "😘", "🤣", "🤗"]
REACTION_DELAYS = [3.6, 4.2, 4.8, 6.3, 2.4]

def get_buttons():
    kb = [
        [types.InlineKeyboardButton(text=DEFAULT_BUTTON_TEXT, url=DEFAULT_SUBSCRIBE_LINK, style=DEFAULT_BUTTON_STYLE)],
        [types.InlineKeyboardButton(text=BTN_SUPPORT, url=SUPPORT_LINK, style=SUPPORT_BUTTON_STYLE)]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

async def handle_response_1(message: types.Message, animate_func):
    text = "تغزل بيه اريد اكزكز واشبع رومانسيه\nاريد اذوب من الغزل\nاريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك"
    buttons = get_buttons()
    await animate_func(message, text, reply_markup=buttons)

async def handle_response_2(message: types.Message, animate_func):
    text = "مو ناوي تدلعني مثل البوتات ترى ازعل منك اصيح المولاي\nيغصص بلاعيمك"
    buttons = get_buttons()
    await animate_func(message, text, reply_markup=buttons)

async def handle_response_3(message: types.Message, animate_func):
    text = "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح"
    buttons = get_buttons()
    await animate_func(message, text, reply_markup=buttons)

async def handle_response_4(message: types.Message, animate_func):
    text = "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
    buttons = get_buttons()
    await animate_func(message, text, reply_markup=buttons)

RESPONSE_HANDLERS = [
    handle_response_1,
    handle_response_2,
    handle_response_3,
    handle_response_4
]
