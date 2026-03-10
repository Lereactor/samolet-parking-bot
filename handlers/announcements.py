import logging

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()


class AnnounceState(StatesGroup):
    waiting_for_text = State()


@router.message(Command("announce"))
async def cmd_announce(message: Message, state: FSMContext, is_moderator: bool, **kwargs):
    if message.chat.type != "private" or not is_moderator:
        return

    await message.answer(
        "📢 Введите текст объявления для всех пользователей:"
    )
    await state.set_state(AnnounceState.waiting_for_text)


@router.message(AnnounceState.waiting_for_text)
async def announce_text(message: Message, state: FSMContext, db, is_moderator: bool, **kwargs):
    if message.chat.type != "private" or not is_moderator:
        return

    text = message.text.strip()
    if len(text) < 5:
        await message.answer("Объявление слишком короткое. Минимум 5 символов:")
        return

    await db.add_announcement(message.from_user.id, text)

    users = await db.get_all_approved_users()
    sent = 0
    failed = 0
    bot: Bot = message.bot

    for user in users:
        try:
            await bot.send_message(
                user["telegram_id"],
                f"📢 <b>Объявление</b>\n\n{text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"✅ Объявление отправлено: {sent} получили, {failed} не доставлено."
    )
    await state.clear()
