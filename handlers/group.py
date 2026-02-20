import re
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message

from config import SOURCE_GROUP

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: Message, db, **kwargs):
    """Handle messages in groups that mention the bot."""
    if not message.text:
        return

    bot: Bot = message.bot
    bot_info = await bot.me()
    bot_username = bot_info.username

    # Check if bot is mentioned
    text = message.text
    is_mentioned = False

    # Check for @username mention
    if bot_username and f"@{bot_username}" in text:
        is_mentioned = True
        text = text.replace(f"@{bot_username}", "").strip()

    # Check for reply to bot's message
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == bot_info.id:
            is_mentioned = True

    # Check entities for bot mention
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = message.text[entity.offset:entity.offset + entity.length]
                if bot_username and mention_text.lower() == f"@{bot_username.lower()}":
                    is_mentioned = True
                    text = message.text[:entity.offset] + message.text[entity.offset + entity.length:]
                    text = text.strip()

    if not is_mentioned:
        return

    # Extract spot number from remaining text
    numbers = re.findall(r"\b(\d{1,4})\b", text)

    if not numbers:
        await message.reply(
            "Укажите номер парковочного места.\n"
            f"Пример: @{bot_username} 142 перегородили выезд"
        )
        return

    spot_number = int(numbers[0])
    # The rest of the text is the message
    message_text = re.sub(r"\b\d{1,4}\b", "", text, count=1).strip()
    if not message_text:
        message_text = "Обращение по поводу вашего места"

    owner = await db.get_spot_owner(spot_number)

    if not owner:
        await message.reply(f"Место {spot_number} не зарегистрировано в системе.")
        return

    # Save message
    from_user_id = message.from_user.id if message.from_user else None
    if from_user_id:
        # Check if sender is registered
        sender = await db.get_user(from_user_id)
        if sender:
            await db.add_message(from_user_id, spot_number, message_text, SOURCE_GROUP)

    # Notify owner via DM
    sender_name = message.from_user.full_name if message.from_user else "Кто-то"
    try:
        await bot.send_message(
            owner["telegram_id"],
            f"💬 <b>Сообщение из группы</b>\n\n"
            f"По поводу места <b>{spot_number}</b>:\n"
            f"«{message_text}»\n\n"
            f"От: {sender_name}",
            parse_mode="HTML",
        )
        await message.reply(f"✅ Владелец места {spot_number} уведомлён.")
    except Exception as e:
        logger.error(f"Failed to DM owner of spot {spot_number}: {e}")
        await message.reply(
            f"⚠️ Не удалось уведомить владельца места {spot_number}. "
            f"Возможно, он не начал диалог с ботом."
        )
