import re
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message

from config import SOURCE_GROUP

logger = logging.getLogger(__name__)
router = Router()

# Cached bot username (populated on first group message)
_bot_username: str | None = None


async def _get_bot_username(bot: Bot) -> str:
    global _bot_username
    if not _bot_username:
        info = await bot.me()
        _bot_username = info.username
    return _bot_username


@router.message(Command("start"), F.chat.type.in_({"group", "supergroup"}))
async def start_in_group(message: Message, **kwargs):
    """Redirect /start in group to DM."""
    bot: Bot = message.bot
    username = await _get_bot_username(bot)
    await message.reply(
        f"👋 Для регистрации и работы с ботом напишите мне в личные сообщения:\n"
        f"👉 @{username}"
    )


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: Message, db, **kwargs):
    """Handle @mention messages in groups — notify spot owner and confirm to sender via DM."""
    if not message.text:
        return

    bot: Bot = message.bot
    bot_username = await _get_bot_username(bot)

    text = message.text
    is_mentioned = False

    # Check via entities (most reliable, case-insensitive)
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = message.text[entity.offset:entity.offset + entity.length]
                if bot_username and mention_text.lower() == f"@{bot_username.lower()}":
                    is_mentioned = True
                    text = (message.text[:entity.offset] + message.text[entity.offset + entity.length:]).strip()
                    break

    # Fallback: plain text check (case-insensitive)
    if not is_mentioned and bot_username:
        lower_text = text.lower()
        lower_mention = f"@{bot_username.lower()}"
        if lower_mention in lower_text:
            is_mentioned = True
            text = re.sub(re.escape(lower_mention), "", lower_text, count=1, flags=re.IGNORECASE).strip()
            # Use original case text with mention removed
            idx = message.text.lower().find(lower_mention)
            if idx >= 0:
                text = (message.text[:idx] + message.text[idx + len(lower_mention):]).strip()

    # Check for reply to bot's message
    if not is_mentioned and message.reply_to_message and message.reply_to_message.from_user:
        bot_info = await bot.get_me()
        if message.reply_to_message.from_user.id == bot_info.id:
            is_mentioned = True

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

    owners = await db.get_spot_owners(spot_number)

    if not owners:
        await message.reply(f"Место {spot_number} не зарегистрировано в системе.")
        return

    # Save message
    from_user_id = message.from_user.id if message.from_user else None
    if from_user_id:
        sender = await db.get_user(from_user_id)
        if sender:
            await db.add_message(from_user_id, spot_number, message_text, SOURCE_GROUP)

    # Notify all owners via DM
    sender_name = message.from_user.full_name if message.from_user else "Кто-то"
    sent = 0
    for owner in owners:
        try:
            await bot.send_message(
                owner["telegram_id"],
                f"💬 <b>Сообщение из группы</b>\n\n"
                f"По поводу места <b>{spot_number}</b>:\n"
                f"«{message_text}»\n\n"
                f"От: {sender_name}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to DM owner of spot {spot_number}: {e}")

    if sent == 0:
        await message.reply(
            f"⚠️ Не удалось уведомить владельца(ев) места {spot_number}. "
            f"Возможно, они не начали диалог с ботом."
        )
        return

    owner_word = "владелец" if sent == 1 else f"владельцы ({sent})"

    # Try to send confirmation to sender via DM
    if from_user_id:
        try:
            await bot.send_message(
                from_user_id,
                f"✅ {owner_word.capitalize()} места {spot_number} уведомлён(ы).\n"
                f"Ответ придёт сюда, в личные сообщения.",
            )
            # Minimal reply in group
            await message.reply(f"✅ Владелец уведомлён — ответ придёт вам в личные сообщения.")
        except Exception:
            # User hasn't started bot DM — reply in group
            await message.reply(
                f"✅ {owner_word.capitalize()} места {spot_number} уведомлён(ы).\n"
                f"Чтобы получать ответы в личку, напишите боту: @{bot_username}"
            )
