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
last_reactions = []
last_times = []
food_idx = 0

async def trigger_reaction(message: types.Message):
    global last_reactions, last_times
    try:
        available_reacts = [r for r in emojis if r not in last_reactions]
        react = random.choice(available_reacts)
        last_reactions.append(react)
        if len(last_reactions) > 6: 
            last_reactions.pop(0)
        
        available_times = [t for t in [2.4, 4.8, 6.3, 4.2, 3.6] if t not in last_times]
        wait_time = random.choice(available_times)
        last_times.append(wait_time)
        if len(last_times) > 2: 
            last_times.pop(0)
        
        await asyncio.sleep(wait_time)
        await message.react([types.ReactionTypeEmoji(emoji=react)])
    except:
        pass

async def type_writer_with_buttons(message: types.Message, text: str):
    global food_idx
    words = text.split()
    chunks = [" ".join(words[i:i+4 if i==0 else i+3]) for i in range(0, len(words), 3)]
    current_text = ""
    
    btn_rari = InlineKeyboardButton(text="راري", url="tg://user?id=8597653867", style="danger")
    btn_support = InlineKeyboardButton(text="ابلاغ الدعم بالمشاكل", url="tg://user?id=8467593882", style="primary")
    
    msg = await message.reply(".")
    asyncio.create_task(trigger_reaction(message))
    
    for idx, chunk in enumerate(chunks):
        current_text += chunk + " "
        await asyncio.sleep(0.3)
        
        btn_pub = eDT.get_public_button()
        if idx == 2:
            kb = InlineKeyboardMarkup(inline_keyboard=[[btn_rari]])
            await msg.edit_text(current_text, reply_markup=kb)
            
            food_msg = await msg.reply(food_emojis[food_idx])
            food_idx = (food_idx + 1) % len(food_emojis)
            asyncio.create_task(trigger_reaction(food_msg))
        elif idx == len(chunks) - 1:
            kb = InlineKeyboardMarkup(inline_keyboard=[[btn_rari], [btn_support], [btn_pub]])
            await msg.edit_text(current_text, reply_markup=kb)
        else:
            await msg.edit_text(current_text)
            
    return msg

async def handle_default_response(message: types.Message):
    global resp_idx
    await type_writer_with_buttons(message, responses[resp_idx])
    resp_idx = (resp_idx + 1) % len(responses)

async def send_startup_messages(bot):
    targets = [8597653867, 8467593882]
    btn_pub = eDT.get_public_button()
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_pub]])
    
    for target_id in targets:
        try:
            msg1 = await bot.send_message(chat_id=target_id, text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!", reply_markup=kb)
            msg2 = await bot.send_message(chat_id=target_id, text=food_emojis[0], reply_to_message_id=msg1.message_id)
            
            asyncio.create_task(trigger_reaction(msg1))
            asyncio.create_task(trigger_reaction(msg2))
        except:
            pass
