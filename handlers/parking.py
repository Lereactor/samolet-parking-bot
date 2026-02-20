import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import MENU_BUTTONS, SOURCE_BLOCKED, SOURCE_SOS

logger = logging.getLogger(__name__)
router = Router()


class BlockedState(StatesGroup):
    waiting_for_spot = State()


class SOSState(StatesGroup):
    waiting_for_spot = State()


class AwayState(StatesGroup):
    selecting_spot = State()
    waiting_for_duration = State()


class DirectoryState(StatesGroup):
    waiting_for_spot = State()


# === My Spot ===

@router.message(F.text == MENU_BUTTONS["my_spot"])
async def my_spot(message: Message, db, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    spots = await db.get_user_spots(message.from_user.id)
    if not spots:
        await message.answer("У вас нет зарегистрированных мест.")
        return

    lines = ["<b>📍 Ваши места:</b>\n"]
    for s in spots:
        status = "🟢 свободно (уехал)" if s["is_temporary_free"] else "🔵 занято (на месте)"
        free_info = ""
        if s["is_temporary_free"] and s["free_until"]:
            free_info = f" — до {s['free_until'].strftime('%d.%m %H:%M')}"
        lines.append(f"Место <b>{s['spot_number']}</b> — {status}{free_info}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# === Blocked (Перегородили!) ===

@router.message(F.text == MENU_BUTTONS["blocked"])
async def blocked_start(message: Message, state: FSMContext, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    await message.answer(
        "🚫 <b>Перегородили выезд?</b>\n\n"
        "Введите номер места машины, которая вас заблокировала:",
        parse_mode="HTML",
    )
    await state.set_state(BlockedState.waiting_for_spot)


@router.message(BlockedState.waiting_for_spot)
async def blocked_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)
    owner = await db.get_spot_owner(spot_number)

    if not owner:
        await message.answer(
            f"Место {spot_number} не зарегистрировано в системе.\n"
            "Попробуйте другой номер или отмените: /start"
        )
        await state.clear()
        return

    # Log the message
    sender_spots = await db.get_user_spots(message.from_user.id)
    sender_spot_text = ", ".join(str(s["spot_number"]) for s in sender_spots) if sender_spots else "?"

    await db.add_message(
        message.from_user.id, spot_number,
        f"Перегородили выезд! (место отправителя: {sender_spot_text})",
        SOURCE_BLOCKED,
    )

    # Notify owner
    bot: Bot = message.bot
    try:
        await bot.send_message(
            owner["telegram_id"],
            f"🚫 <b>Вашу машину просят переставить!</b>\n\n"
            f"Место <b>{spot_number}</b> — вы перегородили выезд.\n"
            f"Обращается владелец места: {sender_spot_text}\n\n"
            f"Пожалуйста, переставьте машину как можно скорее!",
            parse_mode="HTML",
        )
        await message.answer(
            f"✅ Владелец места {spot_number} уведомлён!"
        )
    except Exception as e:
        logger.error(f"Failed to notify spot owner {spot_number}: {e}")
        await message.answer(
            f"⚠️ Не удалось отправить уведомление владельцу места {spot_number}. "
            f"Возможно, он заблокировал бота."
        )

    await state.clear()


# === SOS Alarm ===

@router.message(F.text == MENU_BUTTONS["sos"])
async def sos_start(message: Message, state: FSMContext, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    await message.answer(
        "🚨 <b>SOS — Сигнализация!</b>\n\n"
        "Введите номер места машины, у которой сработала сигнализация:",
        parse_mode="HTML",
    )
    await state.set_state(SOSState.waiting_for_spot)


@router.message(SOSState.waiting_for_spot)
async def sos_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)
    owner = await db.get_spot_owner(spot_number)

    if not owner:
        await message.answer(
            f"Место {spot_number} не зарегистрировано.\n"
            "Попробуйте другой номер или отмените: /start"
        )
        await state.clear()
        return

    await db.add_message(
        message.from_user.id, spot_number,
        "SOS: Сработала сигнализация!",
        SOURCE_SOS,
    )

    bot: Bot = message.bot
    try:
        await bot.send_message(
            owner["telegram_id"],
            f"🚨 <b>СИГНАЛИЗАЦИЯ!</b>\n\n"
            f"У вашей машины на месте <b>{spot_number}</b> сработала сигнализация!\n"
            f"Проверьте автомобиль.",
            parse_mode="HTML",
        )
        await message.answer(f"✅ Владелец места {spot_number} уведомлён!")
    except Exception as e:
        logger.error(f"Failed to notify spot owner {spot_number}: {e}")
        await message.answer(
            f"⚠️ Не удалось уведомить владельца места {spot_number}."
        )

    await state.clear()


# === Away / Back (Уезжаю / Вернулся) ===

@router.message(F.text == MENU_BUTTONS["away"])
async def away_toggle(message: Message, state: FSMContext, db, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    spots = await db.get_user_spots(message.from_user.id)
    if not spots:
        await message.answer("У вас нет зарегистрированных мест.")
        return

    if len(spots) == 1:
        # Single spot — toggle directly
        spot = spots[0]
        if spot["is_temporary_free"]:
            await db.set_spot_free(spot["spot_number"], False)
            await message.answer(
                f"🔵 Место <b>{spot['spot_number']}</b> отмечено как <b>занято</b>. С возвращением!",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"На сколько часов вы уезжаете? (число от 1 до 720)\n"
                f"Или отправьте 0, чтобы не указывать время.",
            )
            await state.update_data(spot_number=spot["spot_number"])
            await state.set_state(AwayState.waiting_for_duration)
    else:
        # Multiple spots — ask which one
        lines = ["Выберите место (введите номер):\n"]
        for s in spots:
            status = "🟢 свободно" if s["is_temporary_free"] else "🔵 занято"
            lines.append(f"  {s['spot_number']} — {status}")
        await message.answer("\n".join(lines))
        await state.set_state(AwayState.selecting_spot)


@router.message(AwayState.selecting_spot)
async def away_select_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места:")
        return

    spot_number = int(text)
    spots = await db.get_user_spots(message.from_user.id)
    user_spot_nums = [s["spot_number"] for s in spots]

    if spot_number not in user_spot_nums:
        await message.answer(f"Это не ваше место. Ваши: {', '.join(str(n) for n in user_spot_nums)}")
        return

    spot = next(s for s in spots if s["spot_number"] == spot_number)
    if spot["is_temporary_free"]:
        await db.set_spot_free(spot_number, False)
        await message.answer(
            f"🔵 Место <b>{spot_number}</b> отмечено как <b>занято</b>. С возвращением!",
            parse_mode="HTML",
        )
        await state.clear()
    else:
        await message.answer(
            f"На сколько часов вы уезжаете? (число от 1 до 720)\n"
            f"Или отправьте 0, чтобы не указывать время.",
        )
        await state.update_data(spot_number=spot_number)
        await state.set_state(AwayState.waiting_for_duration)


@router.message(AwayState.waiting_for_duration)
async def away_duration(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите число часов (или 0):")
        return

    hours = int(text)
    data = await state.get_data()
    spot_number = data["spot_number"]

    free_until = None
    if 1 <= hours <= 720:
        free_until = datetime.now(timezone.utc) + timedelta(hours=hours)

    await db.set_spot_free(spot_number, True, free_until)

    time_info = ""
    if free_until:
        time_info = f" до {free_until.strftime('%d.%m %H:%M')} UTC"

    await message.answer(
        f"🟢 Место <b>{spot_number}</b> отмечено как <b>свободно</b>{time_info}.\n"
        f"Когда вернётесь, нажмите «{MENU_BUTTONS['away']}» снова.",
        parse_mode="HTML",
    )
    await state.clear()


# === Directory ===

@router.message(F.text == MENU_BUTTONS["directory"])
async def directory_start(message: Message, state: FSMContext, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    await message.answer(
        "📋 <b>Справочник мест</b>\n\n"
        "Введите номер места, чтобы проверить его статус.\n"
        "Или отправьте <b>все</b>, чтобы увидеть свободные места.",
        parse_mode="HTML",
    )
    await state.set_state(DirectoryState.waiting_for_spot)


@router.message(DirectoryState.waiting_for_spot)
async def directory_lookup(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip().lower()

    if text in ("все", "all", "свободные"):
        free = await db.get_free_spots()
        if not free:
            await message.answer("Нет временно свободных мест.")
        else:
            lines = ["🟢 <b>Свободные места:</b>\n"]
            for s in free:
                time_info = ""
                if s["free_until"]:
                    time_info = f" (до {s['free_until'].strftime('%d.%m %H:%M')})"
                lines.append(f"Место <b>{s['spot_number']}</b>{time_info}")
            await message.answer("\n".join(lines), parse_mode="HTML")
        await state.clear()
        return

    if not text.isdigit():
        await message.answer("Введите номер места как число или «все»:")
        return

    spot_number = int(text)
    spot = await db.get_spot(spot_number)

    if not spot:
        await message.answer(f"Место {spot_number} не зарегистрировано в системе.")
    elif spot["is_temporary_free"]:
        time_info = ""
        if spot["free_until"]:
            time_info = f" до {spot['free_until'].strftime('%d.%m %H:%M')}"
        await message.answer(
            f"🟢 Место <b>{spot_number}</b> — <b>временно свободно</b>{time_info}",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"🔵 Место <b>{spot_number}</b> — <b>занято</b>",
            parse_mode="HTML",
        )

    await state.clear()


# === Help ===

@router.message(F.text == MENU_BUTTONS["help"])
async def show_help(message: Message, db, is_approved: bool, is_admin: bool, **kwargs):
    text = (
        "🅿️ <b>Parking Bot — Помощь</b>\n\n"

        "<b>Начало работы</b>\n"
        "1. Напишите /start боту в личные сообщения\n"
        "2. Введите ваше имя\n"
        "3. Введите номер(а) парковочных мест по одному, затем напишите <b>готово</b>\n"
        "4. Дождитесь одобрения администратором — вам придёт уведомление\n\n"

        "<b>Кнопки меню</b>\n\n"

        f"<b>{MENU_BUTTONS['blocked']}</b>\n"
        "Вам перегородили выезд? Нажмите эту кнопку и введите номер места "
        "машины, которая вас заблокировала. Владельцу придёт срочное уведомление "
        "с просьбой переставить машину.\n\n"

        f"<b>{MENU_BUTTONS['sos']}</b>\n"
        "Слышите сигнализацию на парковке? Нажмите и введите номер места — "
        "владельцу придёт оповещение проверить автомобиль.\n\n"

        f"<b>{MENU_BUTTONS['away']}</b>\n"
        "Уезжаете — нажмите и укажите на сколько часов. Ваше место будет "
        "отображаться как свободное в справочнике. Вернулись — нажмите ещё раз, "
        "место снова станет занятым. Если у вас несколько мест — бот спросит какое.\n\n"

        f"<b>{MENU_BUTTONS['guest']}</b>\n"
        "Ждёте гостя на машине? Оформите гостевой пропуск: введите описание "
        "гостя (имя или номер машины), укажите место и срок (до 72 часов). "
        "Пропуск автоматически деактивируется по истечении.\n\n"

        f"<b>{MENU_BUTTONS['directory']}</b>\n"
        "Проверьте статус любого места: введите номер — бот покажет, занято оно "
        "или свободно (без раскрытия данных владельца). Напишите <b>все</b>, "
        "чтобы увидеть все временно свободные места.\n\n"

        f"<b>{MENU_BUTTONS['my_spot']}</b>\n"
        "Покажет все ваши места и их текущий статус.\n\n"

        f"<b>{MENU_BUTTONS['add_spot']}</b>\n"
        "Добавить ещё одно парковочное место к вашему аккаунту.\n\n"

        f"<b>{MENU_BUTTONS['remove_spot']}</b>\n"
        "Удалить одно из ваших мест (например, если вы больше его не арендуете).\n\n"

        "<b>Использование в группе</b>\n"
        "Добавьте бота в чат вашего ЖК. Чтобы связаться с владельцем места, "
        "напишите в группе:\n"
        "<code>@Samolet_parking_bot 142 перегородили выезд</code>\n"
        "Бот отправит владельцу места 142 личное сообщение с вашим текстом "
        "и ответит в группе, что владелец уведомлён.\n"
    )

    if is_admin:
        text += (
            "\n\n👑 <b>Администрирование</b>\n\n"

            "<b>Команды:</b>\n"
            "/pending — список заявок на регистрацию, одобрить или отклонить\n"
            "/users — все пользователи, их статусы и места\n"
            "/stats — статистика: пользователи, места, сообщения, гостевые\n"
            "/announce — отправить объявление всем одобренным пользователям\n"
            "/backup — скачать полный бэкап базы данных (JSON)\n"
            "/restore — загрузить бэкап для восстановления\n\n"

            "<b>Управление местами:</b>\n"
            "<code>/spot info 142</code> — кто владелец места 142\n"
            "<code>/spot add 142 228501005</code> — назначить место 142 пользователю с указанным ID\n"
            "<code>/spot remove 142</code> — освободить место 142 (снять с любого владельца)\n\n"

            "<b>Модерация:</b>\n"
            "При одобрении/отклонении заявок используйте кнопки под сообщением о заявке. "
            "ID пользователя можно узнать через /users.\n"
        )

    await message.answer(text, parse_mode="HTML")
