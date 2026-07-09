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
            available_reacts = emojis.copy()
            
        react = random.choice(available_reacts)
        recent_reactions.append(react)
        if len(recent_reactions) > 4:
            recent_reactions.pop(0)
            
        wait_time = random.choice([2.4, 4.8, 6.3, 4.2, 3.6])
        await asyncio.sleep(wait_time)
        await message.react([types.ReactionTypeEmoji(emoji=react)])
    except:
        pass

async def type_writer_with_buttons(message: types.Message, text: str, is_startup=False):
    global food_idx
    words = text.split()
    chunks = [" ".join(words[i:i+4 if i==0 else i+3]) for i in range(0, len(words), 3)]
    
    btn_rari = InlineKeyboardButton(text="راري", url="tg://user?id=8597653867")
    btn_support = InlineKeyboardButton(text="ابلاغ الدعم بالمشاكل", url="tg://user?id=8467593882")
    
    current_text = chunks[0] + " "
    msg = await message.reply(current_text)
    
    if not is_startup:
        asyncio.create_task(trigger_reaction(message))
    
    for idx, chunk in enumerate(chunks[1:], start=1):
        current_text += chunk + " "
        await asyncio.sleep(0.3)
        
        if is_startup:
            if idx == len(chunks) - 1:
                kb = InlineKeyboardMarkup(inline_keyboard=[[btn_rari]])
                await msg.edit_text(current_text, reply_markup=kb)
            else:
                await msg.edit_text(current_text)
        else:
            if idx == 1:
                await msg.edit_text(current_text)
            elif idx >= 2 and idx < len(chunks) - 1:
                kb = InlineKeyboardMarkup(inline_keyboard=[[btn_rari]])
                await msg.edit_text(current_text, reply_markup=kb)
                
                if idx == 2:
                    food_msg = await msg.reply(food_emojis[food_idx])
                    food_idx = (food_idx + 1) % len(food_emojis)
            elif idx == len(chunks) - 1:
                kb = InlineKeyboardMarkup(inline_keyboard=[[btn_rari], [btn_support]])
                await msg.edit_text(current_text, reply_markup=kb)
                
    return msg

async def handle_default_response(message: types.Message):
    global resp_idx
    await type_writer_with_buttons(message, responses[resp_idx])
    resp_idx = (resp_idx + 1) % len(responses)

async def send_startup_messages(bot):
    targets = [8597653867, 8467593882]
    for target_id in targets:
        try:
            fake_msg = types.Message(
                message_id=0,
                date=None,
                chat=types.Chat(id=target_id, type="private"),
                from_user=types.User(id=target_id, is_bot=False, first_name="User"),
                text=""
            )
            fake_msg._bot = bot
            
            msg1 = await type_writer_with_buttons(fake_msg, "اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!", is_startup=True)
            msg2 = await bot.send_message(chat_id=target_id, text=food_emojis[0], reply_to_message_id=msg1.message_id)
        except:
            pass
