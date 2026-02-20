import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import MENU_BUTTONS

logger = logging.getLogger(__name__)
router = Router()


class GuestState(StatesGroup):
    waiting_for_info = State()
    waiting_for_spot = State()
    waiting_for_duration = State()


@router.message(F.text == MENU_BUTTONS["guest"])
async def guest_start(message: Message, state: FSMContext, db, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    # Show active passes first
    active = await db.get_active_guest_passes(message.from_user.id)
    if active:
        lines = ["<b>Активные гостевые пропуска:</b>\n"]
        for g in active:
            expires = g["expires_at"].strftime("%d.%m %H:%M")
            lines.append(f"🎫 {g['guest_info']} — место {g['spot_number']} — до {expires}")
        lines.append("\n")
        await message.answer("\n".join(lines), parse_mode="HTML")

    await message.answer(
        "🎫 <b>Новый гостевой пропуск</b>\n\n"
        "Введите описание гостя (имя, номер машины или что-то для идентификации):",
        parse_mode="HTML",
    )
    await state.set_state(GuestState.waiting_for_info)


@router.message(GuestState.waiting_for_info)
async def guest_info(message: Message, state: FSMContext, **kwargs):
    info = message.text.strip()
    if len(info) < 2 or len(info) > 200:
        await message.answer("Описание от 2 до 200 символов. Попробуйте ещё:")
        return

    await state.update_data(guest_info=info)

    await message.answer(
        "На какое парковочное место приедет гость? (номер):"
    )
    await state.set_state(GuestState.waiting_for_spot)


@router.message(GuestState.waiting_for_spot)
async def guest_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)

    # Verify user owns this spot or spot is free
    user_spots = await db.get_user_spots(message.from_user.id)
    user_spot_nums = [s["spot_number"] for s in user_spots]

    if spot_number not in user_spot_nums:
        spot = await db.get_spot(spot_number)
        if spot and not spot["is_temporary_free"]:
            await message.answer(
                f"Место {spot_number} не ваше и не свободно. "
                f"Ваши места: {', '.join(str(n) for n in user_spot_nums)}"
            )
            return

    await state.update_data(spot_number=spot_number)
    await message.answer("На сколько часов нужен пропуск? (1-72):")
    await state.set_state(GuestState.waiting_for_duration)


@router.message(GuestState.waiting_for_duration)
async def guest_duration(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите количество часов (число от 1 до 72):")
        return

    hours = int(text)
    if hours < 1 or hours > 72:
        await message.answer("Пропуск может быть от 1 до 72 часов:")
        return

    data = await state.get_data()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

    pass_id = await db.add_guest_pass(
        message.from_user.id,
        data["guest_info"],
        data["spot_number"],
        expires_at,
    )

    await message.answer(
        f"✅ <b>Гостевой пропуск оформлен!</b>\n\n"
        f"Гость: {data['guest_info']}\n"
        f"Место: {data['spot_number']}\n"
        f"Действует до: {expires_at.strftime('%d.%m.%Y %H:%M')} UTC\n"
        f"Номер пропуска: #{pass_id}",
        parse_mode="HTML",
    )
    await state.clear()
