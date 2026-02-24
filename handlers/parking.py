import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import MENU_BUTTONS, SOURCE_NOTIFY

UK_PHONE = "+78007752411"

logger = logging.getLogger(__name__)
router = Router()


class NotifyState(StatesGroup):
    waiting_for_spot = State()
    waiting_for_message = State()


class HistoryState(StatesGroup):
    waiting_for_spot = State()


class ReminderState(StatesGroup):
    selecting_spot = State()
    waiting_for_datetime = State()


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
        # Check co-owners
        owners = await db.get_spot_owners(s["spot_number"])
        co_owners = [o for o in owners if o["telegram_id"] != message.from_user.id]
        co_info = ""
        if co_owners:
            co_names = ", ".join(o["name"] for o in co_owners)
            co_info = f" (совладельцы: {co_names})"
        lines.append(f"Место <b>{s['spot_number']}</b>{co_info}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# === Notify (Сообщить А/М) ===

@router.message(F.text == MENU_BUTTONS["notify"])
async def notify_start(message: Message, state: FSMContext, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    await message.answer(
        "✉️ <b>Сообщить авто/мото</b>\n\n"
        "Введите номер места, владельцу которого хотите написать:",
        parse_mode="HTML",
    )
    await state.set_state(NotifyState.waiting_for_spot)


@router.message(NotifyState.waiting_for_spot)
async def notify_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)
    owners = await db.get_spot_owners(spot_number)

    if not owners:
        await message.answer(
            f"Место {spot_number} не зарегистрировано в системе.\n"
            "Попробуйте другой номер или отмените: /start"
        )
        await state.clear()
        return

    await state.update_data(spot_number=spot_number)
    await message.answer("Введите текст сообщения для владельца(ев) места:")
    await state.set_state(NotifyState.waiting_for_message)


@router.message(NotifyState.waiting_for_message)
async def notify_message(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if len(text) < 2:
        await message.answer("Сообщение слишком короткое. Минимум 2 символа:")
        return

    data = await state.get_data()
    spot_number = data["spot_number"]

    # Get sender's spots for context
    sender_spots = await db.get_user_spots(message.from_user.id)
    sender_spot_text = ", ".join(str(s["spot_number"]) for s in sender_spots) if sender_spots else "?"

    # Log the message
    await db.add_message(message.from_user.id, spot_number, text, SOURCE_NOTIFY)

    # Notify all owners
    owners = await db.get_spot_owners(spot_number)
    bot: Bot = message.bot
    sent = 0
    for owner in owners:
        try:
            await bot.send_message(
                owner["telegram_id"],
                f"✉️ <b>Сообщение от А/М {sender_spot_text}</b>\n\n"
                f"По поводу места <b>{spot_number}</b>:\n"
                f"«{text}»",
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to notify owner of spot {spot_number}: {e}")

    if sent > 0:
        owner_word = "владелец" if sent == 1 else f"владельцы ({sent})"
        await message.answer(f"✅ {owner_word.capitalize()} места {spot_number} уведомлён(ы)!")
    else:
        await message.answer(
            f"⚠️ Не удалось отправить уведомление владельцу(ам) места {spot_number}. "
            f"Возможно, они заблокировали бота."
        )

    await state.clear()


# === History (История сообщений) ===

@router.message(F.text == MENU_BUTTONS["history"])
async def history_start(message: Message, state: FSMContext, db, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    spots = await db.get_user_spots(message.from_user.id)
    if not spots:
        await message.answer("У вас нет зарегистрированных мест.")
        return

    if len(spots) == 1:
        # Show messages for the single spot directly
        await _show_history(message, db, spots[0]["spot_number"])
        return

    # Multiple spots — ask which one
    spots_text = ", ".join(str(s["spot_number"]) for s in spots)
    await message.answer(
        f"📨 <b>История сообщений</b>\n\n"
        f"Ваши места: {spots_text}\n"
        f"Введите номер места для просмотра истории\n"
        f"или напишите <b>все</b> для всех мест:",
        parse_mode="HTML",
    )
    await state.set_state(HistoryState.waiting_for_spot)


@router.message(HistoryState.waiting_for_spot)
async def history_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip().lower()

    if text in ("все", "all"):
        messages_list = await db.get_messages_for_user_spots(message.from_user.id, 10)
        await _format_history(message, messages_list, "всем вашим местам")
        await state.clear()
        return

    if not text.isdigit():
        await message.answer("Введите номер места как число или «все»:")
        return

    spot_number = int(text)
    # Verify user owns this spot
    spots = await db.get_user_spots(message.from_user.id)
    user_spot_nums = [s["spot_number"] for s in spots]
    if spot_number not in user_spot_nums:
        await message.answer(f"Это не ваше место. Ваши: {', '.join(str(n) for n in user_spot_nums)}")
        return

    await _show_history(message, db, spot_number)
    await state.clear()


async def _show_history(message: Message, db, spot_number: int):
    messages_list = await db.get_messages_for_spot(spot_number, 10)
    await _format_history(message, messages_list, f"месту {spot_number}")


async def _format_history(message: Message, messages_list, label: str):
    if not messages_list:
        await message.answer(f"Нет сообщений по {label}.")
        return

    lines = [f"📨 <b>Последние сообщения по {label}:</b>\n"]
    for m in messages_list:
        date = m["created_at"].strftime("%d.%m %H:%M")
        from_name = m.get("from_name") or "Неизвестный"
        source_icon = {"group": "💬", "notify": "✉️", "private": "📩"}.get(m["source"], "📩")
        lines.append(
            f"{source_icon} <b>{date}</b> — {from_name} → место {m['to_spot']}\n"
            f"   {m['message_text']}"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


# === Reminder (Напомнить об оплате) ===

@router.message(F.text == MENU_BUTTONS["reminder"])
async def reminder_start(message: Message, state: FSMContext, db, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    spots = await db.get_user_spots(message.from_user.id)
    if not spots:
        await message.answer("У вас нет зарегистрированных мест.")
        return

    # Show active reminders
    active = await db.get_user_reminders(message.from_user.id)
    if active:
        lines = ["<b>Активные напоминания:</b>\n"]
        for r in active:
            # Convert UTC to MSK (UTC+3) for display
            msk_time = r["remind_at"].astimezone(timezone(timedelta(hours=3)))
            lines.append(f"⏰ Место {r['spot_number']} — {msk_time.strftime('%d.%m.%Y %H:%M')} МСК")
        lines.append("")
        await message.answer("\n".join(lines), parse_mode="HTML")

    if len(spots) == 1:
        await state.update_data(spot_number=spots[0]["spot_number"])
        await message.answer(
            f"⏰ <b>Напоминание для места {spots[0]['spot_number']}</b>\n\n"
            f"Введите дату и время напоминания в формате:\n"
            f"<b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (время московское)\n\n"
            f"Например: <b>15.03.2026 10:00</b>",
            parse_mode="HTML",
        )
        await state.set_state(ReminderState.waiting_for_datetime)
    else:
        spots_text = ", ".join(str(s["spot_number"]) for s in spots)
        await message.answer(
            f"⏰ <b>Напоминание об оплате</b>\n\n"
            f"Ваши места: {spots_text}\n"
            f"Введите номер места:",
            parse_mode="HTML",
        )
        await state.set_state(ReminderState.selecting_spot)


@router.message(ReminderState.selecting_spot)
async def reminder_select_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)
    spots = await db.get_user_spots(message.from_user.id)
    user_spot_nums = [s["spot_number"] for s in spots]

    if spot_number not in user_spot_nums:
        await message.answer(f"Это не ваше место. Ваши: {', '.join(str(n) for n in user_spot_nums)}")
        return

    await state.update_data(spot_number=spot_number)
    await message.answer(
        f"⏰ <b>Напоминание для места {spot_number}</b>\n\n"
        f"Введите дату и время напоминания в формате:\n"
        f"<b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (время московское)\n\n"
        f"Например: <b>15.03.2026 10:00</b>",
        parse_mode="HTML",
    )
    await state.set_state(ReminderState.waiting_for_datetime)


@router.message(ReminderState.waiting_for_datetime)
async def reminder_datetime(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()

    try:
        # Parse as Moscow time (UTC+3)
        msk_tz = timezone(timedelta(hours=3))
        dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
        dt_msk = dt.replace(tzinfo=msk_tz)
        dt_utc = dt_msk.astimezone(timezone.utc)
    except ValueError:
        await message.answer(
            "Неверный формат. Используйте <b>ДД.ММ.ГГГГ ЧЧ:ММ</b>\n"
            "Например: <b>15.03.2026 10:00</b>",
            parse_mode="HTML",
        )
        return

    if dt_utc <= datetime.now(timezone.utc):
        await message.answer("Дата должна быть в будущем. Попробуйте ещё:")
        return

    data = await state.get_data()
    spot_number = data["spot_number"]

    reminder_id = await db.add_reminder(message.from_user.id, spot_number, dt_utc)

    await message.answer(
        f"✅ <b>Напоминание установлено!</b>\n\n"
        f"Место: {spot_number}\n"
        f"Когда: {dt_msk.strftime('%d.%m.%Y %H:%M')} МСК\n"
        f"Номер: #{reminder_id}",
        parse_mode="HTML",
    )
    await state.clear()


# === Directory ===

@router.message(F.text == MENU_BUTTONS["directory"])
async def directory_start(message: Message, state: FSMContext, db, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    # Show summary first
    all_spots = await db.get_all_spots()
    if all_spots:
        # Collect unique spot numbers
        spot_nums = sorted(set(s["spot_number"] for s in all_spots))
        lines = [
            f"📋 <b>Справочник мест</b>\n",
            f"Зарегистрировано мест: {len(spot_nums)}",
            f"Занятые: {', '.join(str(n) for n in spot_nums)}\n",
            "Введите номер места, чтобы проверить его статус.",
        ]
    else:
        lines = [
            "📋 <b>Справочник мест</b>\n",
            "Пока не зарегистрировано ни одного места.\n",
            "Введите номер места для проверки.",
        ]

    await message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(DirectoryState.waiting_for_spot)


@router.message(DirectoryState.waiting_for_spot)
async def directory_lookup(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)
    owners = await db.get_spot_owners(spot_number)

    if not owners:
        await message.answer(f"Место {spot_number} не зарегистрировано в системе.")
    else:
        await message.answer(
            f"🔵 Место <b>{spot_number}</b> — <b>занято</b>",
            parse_mode="HTML",
        )

    await state.clear()


# === Contact UK ===

@router.message(F.text == MENU_BUTTONS["contact_uk"])
async def contact_uk(message: Message, **kwargs):
    await message.answer(
        f"📞 <b>Управляющая компания</b>\n\n"
        f"Телефон: {UK_PHONE}",
        parse_mode="HTML",
    )


# === Help ===

@router.message(F.text == MENU_BUTTONS["help"])
async def show_help(message: Message, db, is_approved: bool, is_admin: bool, is_moderator: bool, **kwargs):
    text = (
        "🅿️ <b>Parking Bot — Помощь</b>\n\n"

        "<b>Начало работы</b>\n"
        "1. Напишите /start боту в личные сообщения\n"
        "2. Введите ваше имя\n"
        "3. Введите номер(а) парковочных мест по одному, затем напишите <b>готово</b>\n"
        "4. Дождитесь одобрения — вам придёт уведомление\n\n"

        "<b>Кнопки меню</b>\n\n"

        f"<b>{MENU_BUTTONS['notify']}</b>\n"
        "Написать владельцу(ам) конкретного места. Введите номер места "
        "и текст сообщения — все владельцы получат уведомление "
        "с указанием вашего места.\n\n"

        f"<b>{MENU_BUTTONS['directory']}</b>\n"
        "Справочник зарегистрированных мест. Покажет сводку и позволит "
        "проверить статус конкретного места.\n\n"

        f"<b>{MENU_BUTTONS['my_spot']}</b>\n"
        "Покажет все ваши места и совладельцев.\n\n"

        f"<b>{MENU_BUTTONS['history']}</b>\n"
        "Просмотреть последние сообщения по вашим местам.\n\n"

        f"<b>{MENU_BUTTONS['reminder']}</b>\n"
        "Установить напоминание об оплате парковки. Укажите дату и время "
        "(московское) — бот пришлёт уведомление.\n\n"

        f"<b>{MENU_BUTTONS['add_spot']}</b>\n"
        "Добавить ещё одно парковочное место к вашему аккаунту.\n\n"

        f"<b>{MENU_BUTTONS['remove_spot']}</b>\n"
        "Удалить одно из ваших мест.\n\n"

        f"<b>{MENU_BUTTONS['contact_uk']}</b>\n"
        f"Телефон управляющей компании: {UK_PHONE}\n\n"

        "<b>Использование в группе</b>\n"
        "Добавьте бота в чат вашего ЖК. Чтобы связаться с владельцем места, "
        "напишите в группе:\n"
        "<code>@Samolet_parking_bot 142 перегородили выезд</code>\n"
        "Бот отправит владельцу(ам) места 142 личное сообщение.\n"
    )

    if is_moderator:
        text += (
            "\n\n🛡 <b>Модерация</b>\n\n"

            "<b>Команды:</b>\n"
            "/pending — список заявок на регистрацию\n"
            "/announce — отправить объявление всем\n\n"

            "<b>Управление местами:</b>\n"
            "<code>/spot info 142</code> — кто владелец(ы) места\n"
            "<code>/spot add 142 228501005</code> — назначить место пользователю\n"
            "<code>/spot remove 142</code> — освободить место\n"
            "<code>/spot force 142 228501005</code> — добавить совладельца\n"
        )

    if is_admin:
        text += (
            "\n\n👑 <b>Администрирование</b>\n\n"

            "/users — все пользователи, их статусы и места\n"
            "/stats — статистика\n"
            "/backup — скачать полный бэкап БД (JSON)\n"
            "/restore — загрузить бэкап для восстановления\n\n"

            "👥 <b>Управление модераторами:</b>\n"
            "<code>/mod add UserID</code> — назначить модератора\n"
            "<code>/mod remove UserID</code> — снять модератора\n"
            "<code>/mod list</code> — список модераторов\n"
        )

    await message.answer(text, parse_mode="HTML")
