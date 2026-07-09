import random
import re
from aiogram import types
from aiogram.enums import ChatType

DEVELOPER_ID = "8597653867"
SUPPORT_ID = "8467593882"
ALLOWED_DEVELOPERS = [int(DEVELOPER_ID), int(SUPPORT_ID)]

PROGRESS_START = "انتظر لأتمعن النظر على الرابط وتفقده\nسيتم ارسال الميديا"
PROGRESS_TEMPLATE = "{percent}%"
ERROR_MESSAGE = "الرابط غير مدعوم او الموقع مو مدعوم\nشم كسي ويصير مدعوم ههع امزح دادي"
FILE_NOT_FOUND = ERROR_MESSAGE

SUCCESS_MESSAGE = "يدلل بعد كسي\nترى اموت بيك اعشقك هايمه بعيرك"
STARTUP_MESSAGE = "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!"
QUEUE_FULL_MESSAGE = "سته عمليات داشتغل عليهم وبعدك تريد\nلعد شكد ملعوب بعرضك"

REACTION_EMOJIS = ["🥰", "😡", "😭", "🍓", "😘", "🤣", "🤗"]
REACTION_DELAYS = [3.6, 4.2, 4.8, 6.3, 2.4]

FOOD_EMOJIS = ["🥪", "🌭", "🥞", "🍔", "🍣", "🍕", "🍟"]

BTN_MUTE = "قفل الاشعارات"
BTN_UNMUTE = "فتح الاشعارات"
BTN_CANCEL = "مسح"

BTN_SET_LINK = "تعيين الرابط"
BTN_SHOW_MSG = "عرض مسج الاشتراك"

MUTE_SUCCESS_MSG = "¹# - تم قفل النقل مولاي\nيدلل تاج راسي"
UNMUTE_SUCCESS_MSG = "¹# - تم فتح النقل مولاي\nيدلل تاج راسي"
CANCEL_SUCCESS_MSG = "صار وتدلل\nمنو يكدر يعصيك يبعد كسي اه"
PANEL_TITLE_MSG = "ازرار الاوامر كدامك عدل التريدا\nبكيفك يبعدي"

BOT_EDIT_PANEL_MSG = "تريد عرض مسج الاشتراك الفرضي دوس عرض\nهم لو تريد تعين\nرابط زر الاشتراك دوس تعيين الرابط"
ASK_LINK_MSG = "ارسل يوزر / رابط القناة او الكروب\nيلا مولاي"
INVALID_LINK_MSG = "اهو ليش تسوي هيج وياي ابوس زبك\nلاتعيدها مولاي"
SET_LINK_SUCCESS_MSG = "تم تعيين زر الاشتراك الفرضي مثل ماردت\nسمعا وطاعة العيرك"

FORCE_SUB_TEXT = "اشترك بالقناة لو ماراح يشتغل\nوياك البوت ضروري عيني"

def get_keyboard_markup(invoker_id: int):
    kb = [
        [
            types.InlineKeyboardButton(text=BTN_MUTE, switch_inline_query_current_chat="قفل الاشعارات"),
            types.InlineKeyboardButton(text=BTN_UNMUTE, switch_inline_query_current_chat="فتح الاشعارات")
        ],
        [
            types.InlineKeyboardButton(text=BTN_CANCEL, callback_data=f"btn_delete_{invoker_id}", style="primary")
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_bot_edit_keyboard():
    kb = [
        [types.KeyboardButton(text=BTN_SET_LINK), types.KeyboardButton(text=BTN_SHOW_MSG)],
        [types.KeyboardButton(text="الغاء")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

async def get_force_sub_inline(link: str) -> types.InlineKeyboardMarkup:
    if not link:
        buttons = [[types.InlineKeyboardButton(text="لم يتم التعيين بعد", url=f"tg://user?id={DEVELOPER_ID}", style="primary")]]
    else:
        final_url = link
        if not link.startswith("http://") and not link.startswith("https://"):
            clean_username = link.replace("@", "")
            final_url = f"https://t.me/{clean_username}"
        buttons = [[types.InlineKeyboardButton(text="اشترك بالقناة", url=final_url, style="primary")]]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

async def is_user_allowed_for_edit(message: types.Message) -> bool:
    chat_type = message.chat.type
    user_id = message.from_user.id if message.from_user else None

    if chat_type == ChatType.PRIVATE:
        return user_id in ALLOWED_DEVELOPERS if user_id else False

    elif chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if user_id and user_id in ALLOWED_DEVELOPERS:
            return True
        if user_id:
            try:
                member = await message.chat.get_member(user_id)
                return member.status in ['creator', 'administrator']
            except Exception:
                return False
        return False

    elif chat_type == ChatType.CHANNEL:
        if user_id and user_id in ALLOWED_DEVELOPERS:
            return True
        return True

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
