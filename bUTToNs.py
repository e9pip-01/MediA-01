import asyncio
import random
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import eDT

responses = [
    "تغزل بيه اريد اكزكز واشبع رومانسيه\nاريد اذوب من الغزل\nاريد اموع وافقد من الدلال اريد كسي ينكع بدون فرك",
    "مو ناوي تدلعني مثل البوتات ترى ازعل منك اصيح المولاي\nيغصص بلاعيمك",
    "تريد اكلك شعر علمود توافق تدللني وتدلعني\nوترضى عليه مو",
    "من اشوف زبك يسعبل كسي وتذوب الروح انزل\nالعيرك ذليلة امصة ولباسي مشلوح",
    "انزع لباسي الك وتشم عطر كسي اليفوح شكني\nبعيرك وضرط طيزي ترى فدوة الك اروح"
]

emojis = ["🥰", "😭", "🤗", "😘", "🍓", "🍌", "🤣"]
food_emojis = ["🍟", "🍔", "🍕", "🥪", "🍣", "🥞", "🌭"]

resp_idx = 0
food_idx = 0
recent_reactions = []

async def trigger_reaction(message: types.Message):
    global recent_reactions
    try:
        available_reacts = [r for r in emojis if r not in recent_reactions]
        if not available_reacts:
            recent_reactions.clear()
            available_reacts = emojis
            
        react = random.choice(available_reacts)
        recent_reactions.append(react)
        if len(recent_reactions) > 4:
            recent_reactions.pop(0)
            
        wait_times = [2.4, 4.8, 6.3, 4.2, 3.6]
        await asyncio.sleep(random.choice(wait_times))
        await message.react([types.ReactionTypeEmoji(emoji=react)])
    except:
        pass

async def type_writer_with_buttons(message: types.Message, text: str):
    global food_idx
    lines = text.split('\n')
    
    btn_rari = InlineKeyboardButton(text="راري", url="tg://user?id=8597653867", style="danger")
    btn_support = InlineKeyboardButton(text="ابلاغ الدعم بالمشاكل", url="tg://user?id=8467593882", style="primary")
    
    current_text = lines[0]
    msg = await message.reply(current_text)
    asyncio.create_task(trigger_reaction(message))
    
    if len(lines) > 1:
        for line in lines[1:]:
            await asyncio.sleep(0.4)
            current_text += "\n" + line
            await msg.edit_text(current_text)
            
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_rari], [btn_support]])
    await msg.edit_text(current_text, reply_markup=kb)
    
    food_msg = await msg.reply(food_emojis[food_idx])
    food_idx = (food_idx + 1) % len(food_emojis)
    asyncio.create_task(trigger_reaction(food_msg))
    
    return msg

async def handle_default_response(message: types.Message):
    global resp_idx
    await type_writer_with_buttons(message, responses[resp_idx])
    resp_idx = (resp_idx + 1) % len(responses)

async def send_startup_messages(bot):
    targets = [8597653867, 8467593882]
    btn_dev = InlineKeyboardButton(text="تواصل مع المطور", url="tg://user?id=8597653867")
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_dev]])
    
    for target_id in targets:
        try:
            msg1 = await bot.send_message(chat_id=target_id, text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!", reply_markup=kb)
            msg2 = await bot.send_message(chat_id=target_id, text=food_emojis[0], reply_to_message_id=msg1.message_id)
            
            asyncio.create_task(trigger_reaction(msg1))
            asyncio.create_task(trigger_reaction(msg2))
        except:
            pass
