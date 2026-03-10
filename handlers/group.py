import re
import logging

from aiogram import Router, Bot
from aiogram.types import Message

from config import SOURCE_GROUP

logger = logging.getLogger(__name__)
router = Router()


@router.message()
async def handle_group_message(message: Message, db, **kwargs):
    # Only handle group/supergroup messages
    if message.chat.type not in ("group", "supergroup"):
        return
    if not message.text:
        return

    try:
        bot: Bot = message.bot
        bot_info = await bot.get_me()
        bot_mention = f"@{bot_info.username}".lower()

        # Check if bot is mentioned
        if bot_mention not in message.text.lower():
            return

        # Only registered approved users can send notifications
        if not message.from_user:
            return
        sender = await db.get_user(message.from_user.id)
        if not sender or sender["status"] != "approved":
            await message.reply("⛔ Уведомления могут отправлять только зарегистрированные жители.")
            return

        # Get sender's spots for signature
        sender_spots = await db.get_user_spots(sender["telegram_id"])
        if sender_spots:
            spot_numbers_str = ", ".join(str(s["spot_number"]) for s in sender_spots)
            sender_label = f"Место {spot_numbers_str}"
        else:
            sender_label = sender["name"] or "Житель"

        # Remove mention, find spot number
        clean = message.text.lower().replace(bot_mention, "").strip()
        numbers = re.findall(r"\b(\d{1,4})\b", clean)

        if not numbers:
            await message.reply(
                f"Укажите номер парковочного места.\n"
                f"Пример: @{bot_info.username} 142 перегородили выезд"
            )
            return

        spot_number = int(numbers[0])
        owners = await db.get_spot_owners(spot_number)

        if not owners:
            await message.reply(f"Место {spot_number} не зарегистрировано в системе.")
            return

        # Build message text (remove spot number from clean text)
        message_text = re.sub(r"\b" + numbers[0] + r"\b", "", clean, count=1).strip()
        if not message_text:
            message_text = "Обращение по поводу вашего места"

        # Log
        await db.add_message(message.from_user.id, spot_number, message_text, SOURCE_GROUP)

        # DM all owners
        sent = 0
        for owner in owners:
            try:
                await bot.send_message(
                    owner["telegram_id"],
                    f"💬 <b>Сообщение из группы</b>\n\n"
                    f"По поводу места <b>{spot_number}</b>:\n"
                    f"«{message_text}»\n\n"
                    f"От: {sender_label}",
                    parse_mode="HTML",
                )
                sent += 1
            except Exception as e:
                logger.error(f"Failed to DM owner {owner['telegram_id']}: {e}")

        if sent == 0:
            await message.reply(
                f"⚠️ Не удалось уведомить владельца места {spot_number}.\n"
                f"Владелец должен написать боту /start в личные сообщения."
            )
            return

        # Try DM to sender, fallback to group reply
        if message.from_user:
            try:
                await bot.send_message(
                    message.from_user.id,
                    f"✅ Уведомление отправлено владельцу места {spot_number}.",
                )
                await message.reply("✅ Уведомление отправлено.")
            except Exception:
                await message.reply(
                    f"✅ Владелец места {spot_number} уведомлён.\n"
                    f"Чтобы получать ответы в личку — напишите боту: @{bot_info.username}"
                )

    except Exception as e:
        logger.error(f"handle_group_message error: {e}", exc_info=True)
