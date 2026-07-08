import random
import re
from aiogram import types
from aiogram.enums import ChatType

DEVELOPER_ID = "8597653867"
SUPPORT_ID = "8467593882"

PROGRESS_START = "انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا"
PROGRESS_TEMPLATE = "انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا {percent}%"
ERROR_MESSAGE = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
FILE_NOT_FOUND = ERROR_MESSAGE

SUCCESS_MESSAGE = "يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك"
STARTUP_MESSAGE = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
QUEUE_FULL_MESSAGE = "سته عمليات داشتغل عليهم وبعدك تريد\nلعد شكد ملعوب بعرضك"

REACTION_EMOJIS = ["🥰", "😡", "😭", "🍓", "😘", "🤣", "🤗"]
REACTION_DELAYS = [3.6, 4.2, 4.8, 6.3, 2.4]

BTN_MUTE = "قفل الاشعارات"
BTN_UNMUTE = "فتح الاشعارات"
BTN_CANCEL = "الغاء"

MUTE_SUCCESS_MSG = "¹# - تم قفل الاشعارات مولاي\nكل الاشعارات"
UNMUTE_SUCCESS_MSG = "¹# - تم فتح الاشعارات مولاي\nكل الاشعارات"
CANCEL_SUCCESS_MSG = "صار وتدلل\nمنو يكدر يعصيك يبعد كسي اه"
PANEL_TITLE_MSG = "ازرار الاوامر كدامك عدل التريدا\nبكيفك يبعدي"

def get_keyboard_markup():
    kb = [
        [types.KeyboardButton(text=BTN_MUTE), types.KeyboardButton(text=BTN_UNMUTE)],
        [types.KeyboardButton(text=BTN_CANCEL)]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

async def is_user_allowed_for_edit(message: types.Message) -> bool:
    chat_type = message.chat.type
    user_id = message.from_user.id if message.from_user else message.chat.id
    
    if chat_type == ChatType.PRIVATE:
        return str(user_id) == DEVELOPER_ID
        
    elif chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        try:
            member = await message.chat.get_member(user_id)
            return member.status in ['creator', 'administrator']
        except Exception:
            return False
            
    elif chat_type == ChatType.CHANNEL:
        try:
            member = await message.chat.get_member(user_id)
            return member.status == 'creator'
        except Exception:
            return False
            
    return False

async def handle_response_1(message: types.Message, animate_func):
    text = "تغزل بيه اريد اكزكز واشبع رومانسيه\nاريد اذوب من الغزل\nاريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك"
    await animate_func(message, text, reply_markup=None)

async def handle_response_2(message: types.Message, animate_func):
    text = "مو ناوي تدلعني مثل البوتات ترى ازعل منك اصيح المولاي\nيغصص بلاعيمك"
    await animate_func(message, text, reply_markup=None)

async def handle_response_3(message: types.Message, animate_func):
    text = "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح"
    await animate_func(message, text, reply_markup=None)

async def handle_response_4(message: types.Message, animate_func):
    text = "انزع لباسي الك وتنيكني يبعد كل طموح شكني\nبعيرك وضرطني العافيه ترى فدوة الك اروح"
    await animate_func(message, text, reply_markup=None)

RESPONSE_HANDLERS = [
    handle_response_1,
    handle_response_2,
    handle_response_3,
    handle_response_4
]
