import logging

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)
router = Router()


class AnnounceState(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirm = State()


def _confirm_keyboard(recipient_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Отправить ({recipient_count})",
                    callback_data="announce_send",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="announce_cancel"),
            ]
        ]
    )


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

    users = await db.get_all_approved_users()
    recipient_count = len(users)

    await state.update_data(announce_text=text)
    await state.set_state(AnnounceState.waiting_for_confirm)

    await message.answer(
        f"📢 <b>Предпросмотр объявления</b>\n\n{text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Будет отправлено <b>{recipient_count}</b> пользователям. Подтвердить?",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(recipient_count),
    )


@router.callback_query(AnnounceState.waiting_for_confirm, F.data == "announce_cancel")
async def announce_cancel(callback: CallbackQuery, state: FSMContext, **kwargs):
    await state.clear()
    await callback.message.edit_text("❌ Объявление отменено.")
    await callback.answer()


@router.callback_query(AnnounceState.waiting_for_confirm, F.data == "announce_send")
async def announce_send(callback: CallbackQuery, state: FSMContext, db, **kwargs):
    data = await state.get_data()
    text = data.get("announce_text")
    if not text:
        await state.clear()
        await callback.message.edit_text("⚠️ Текст потерян, начните заново через /announce")
        await callback.answer()
        return

    await db.add_announcement(callback.from_user.id, text)

    users = await db.get_all_approved_users()
    sent = 0
    failed = 0
    bot: Bot = callback.bot

    await callback.message.edit_text(f"📤 Отправляю {len(users)} пользователям…")
    await callback.answer()

    for user in users:
        try:
            await bot.send_message(
                user["telegram_id"],
                f"📢 <b>Объявление</b>\n\n{text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Announce delivery failed for {user['telegram_id']}: {e}")

    await callback.message.edit_text(
        f"✅ Объявление отправлено: {sent} получили, {failed} не доставлено."
    )
    await state.clear()
