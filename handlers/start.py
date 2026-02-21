import io
import json
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile,
)

from config import STAFF_IDS, MENU_BUTTONS

logger = logging.getLogger(__name__)
router = Router()


class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_spot = State()


class AddSpotState(StatesGroup):
    waiting_for_spot = State()


class RemoveSpotState(StatesGroup):
    waiting_for_spot = State()


class AdminSpotState(StatesGroup):
    waiting_for_action = State()


class BackupState(StatesGroup):
    waiting_for_file = State()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_BUTTONS["blocked"]),
             KeyboardButton(text=MENU_BUTTONS["sos"])],
            [KeyboardButton(text=MENU_BUTTONS["away"]),
             KeyboardButton(text=MENU_BUTTONS["guest"])],
            [KeyboardButton(text=MENU_BUTTONS["directory"]),
             KeyboardButton(text=MENU_BUTTONS["my_spot"])],
            [KeyboardButton(text=MENU_BUTTONS["add_spot"]),
             KeyboardButton(text=MENU_BUTTONS["remove_spot"])],
            [KeyboardButton(text=MENU_BUTTONS["contact_uk"]),
             KeyboardButton(text=MENU_BUTTONS["help"])],
        ],
        resize_keyboard=True,
    )


# === /start ===

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db, is_admin: bool, is_moderator: bool, user_status: str, **kwargs):
    await state.clear()

    if user_status == "approved":
        staff_hint = ""
        if is_admin:
            staff_hint = (
                "\n\n🛡 <b>Модерация:</b>\n"
                "/pending — заявки на одобрение\n"
                "/announce — объявление\n"
                "/spot — управление местами\n\n"
                "👑 <b>Администрирование:</b>\n"
                "/users — все пользователи\n"
                "/stats — статистика\n"
                "/backup — экспорт БД\n"
                "/restore — импорт БД"
            )
        elif is_moderator:
            staff_hint = (
                "\n\n🛡 <b>Модерация:</b>\n"
                "/pending — заявки на одобрение\n"
                "/announce — объявление\n"
                "/spot — управление местами"
            )
        await message.answer(
            f"Вы уже зарегистрированы! Используйте меню ниже.{staff_hint}",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    if user_status == "pending":
        await message.answer(
            "⏳ Ваша заявка на рассмотрении. Ожидайте одобрения администратором."
        )
        return

    if user_status == "rejected":
        await message.answer("❌ Ваша заявка была отклонена.")
        return

    if user_status == "banned":
        await message.answer("🚫 Вы заблокированы.")
        return

    # New user — start registration
    await message.answer(
        "🅿️ <b>Parking Bot — парковка ЖК</b>\n\n"
        "Для регистрации введите ваше имя (как к вам обращаться):",
        parse_mode="HTML",
    )
    await state.set_state(RegistrationState.waiting_for_name)


@router.message(RegistrationState.waiting_for_name)
async def registration_name(message: Message, state: FSMContext, **kwargs):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Имя должно быть от 2 до 50 символов. Попробуйте ещё:")
        return

    await state.update_data(name=name, spots=[])
    await message.answer(
        f"Отлично, {name}! Введите номер парковочного места (число).\n"
        f"Можно добавить несколько — вводите по одному.\n"
        f"Когда закончите, отправьте <b>готово</b>.",
        parse_mode="HTML",
    )
    await state.set_state(RegistrationState.waiting_for_spot)


@router.message(RegistrationState.waiting_for_spot)
async def registration_spot(message: Message, state: FSMContext, db, is_admin: bool, is_moderator: bool, **kwargs):
    text = message.text.strip().lower()

    # Finish adding spots
    if text in ("готово", "done", "всё", "все"):
        data = await state.get_data()
        name = data["name"]
        spots = data.get("spots", [])

        if not spots:
            await message.answer("Вы не добавили ни одного места. Введите номер места:")
            return

        # Save user
        await db.add_user(message.from_user.id, message.from_user.username, name)

        spots_text = ", ".join(str(s) for s in spots)

        if is_moderator:
            # Auto-approve staff (admin + moderators)
            await db.set_user_status(message.from_user.id, "approved")
            for spot_number in spots:
                await db.add_spot(spot_number, message.from_user.id)
            await state.clear()
            if is_admin:
                await message.answer(
                    f"👑 Вы зарегистрированы как администратор!\n\n"
                    f"Имя: {name}\n"
                    f"Места: {spots_text}\n\n"
                    f"🛡 Модерация:\n"
                    f"/pending — заявки\n"
                    f"/announce — объявление\n"
                    f"/spot — управление местами\n\n"
                    f"👑 Администрирование:\n"
                    f"/users — пользователи\n"
                    f"/stats — статистика\n"
                    f"/backup — экспорт БД\n"
                    f"/restore — импорт БД",
                    reply_markup=main_menu_keyboard(),
                )
            else:
                await message.answer(
                    f"🛡 Вы зарегистрированы как модератор!\n\n"
                    f"Имя: {name}\n"
                    f"Места: {spots_text}\n\n"
                    f"Команды модерации:\n"
                    f"/pending — заявки\n"
                    f"/announce — объявление\n"
                    f"/spot — управление местами",
                    reply_markup=main_menu_keyboard(),
                )
        else:
            await state.clear()
            await message.answer(
                f"✅ Заявка отправлена!\n\n"
                f"Имя: {name}\n"
                f"Места: {spots_text}\n\n"
                f"Ожидайте одобрения администратором."
            )
            # Notify all staff (admin + moderators)
            bot: Bot = message.bot
            for admin_id in STAFF_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"📋 <b>Новая заявка</b>\n\n"
                        f"Имя: {name}\n"
                        f"Места: {spots_text}\n"
                        f"Username: @{message.from_user.username or 'нет'}\n"
                        f"ID: <code>{message.from_user.id}</code>",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="✅ Одобрить",
                                    callback_data=f"approvemulti_{message.from_user.id}",
                                ),
                                InlineKeyboardButton(
                                    text="❌ Отклонить",
                                    callback_data=f"reject_{message.from_user.id}",
                                ),
                            ]
                        ]),
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
        return

    # Add a spot number
    if not text.isdigit():
        await message.answer("Введите номер места как число (например: 142) или <b>готово</b>:", parse_mode="HTML")
        return

    spot_number = int(text)
    if spot_number < 1 or spot_number > 9999:
        await message.answer("Номер места должен быть от 1 до 9999:")
        return

    existing = await db.get_spot(spot_number)
    if existing:
        await message.answer(
            f"Место {spot_number} уже зарегистрировано за другим пользователем.\n"
            "Введите другой номер:"
        )
        return

    data = await state.get_data()
    spots = data.get("spots", [])
    if spot_number in spots:
        await message.answer(f"Место {spot_number} уже в вашем списке. Введите другой номер или <b>готово</b>:", parse_mode="HTML")
        return

    spots.append(spot_number)
    await state.update_data(spots=spots)
    await message.answer(
        f"✅ Место {spot_number} добавлено. Ваши места: {', '.join(str(s) for s in spots)}\n\n"
        f"Введите ещё номер или отправьте <b>готово</b>.",
        parse_mode="HTML",
    )


# === Admin: approve/reject ===

@router.callback_query(F.data.startswith("approvemulti_"))
async def approve_user_multi(callback: CallbackQuery, db, is_moderator: bool, **kwargs):
    """Approve user and assign all their pending spots."""
    if not is_moderator:
        await callback.answer("Только для модератора или администратора", show_alert=True)
        return

    user_id = int(callback.data.split("_")[1])

    # Parse spot numbers from the message text
    import re
    msg_text = callback.message.text or ""
    spots_match = re.search(r"Места?:\s*([\d,\s]+)", msg_text)
    spot_numbers = []
    if spots_match:
        spot_numbers = [int(n.strip()) for n in spots_match.group(1).split(",") if n.strip().isdigit()]

    await db.set_user_status(user_id, "approved")

    assigned = []
    failed = []
    for spot_number in spot_numbers:
        success = await db.add_spot(spot_number, user_id)
        if success:
            assigned.append(str(spot_number))
        else:
            failed.append(str(spot_number))

    result = f"\n\n✅ Одобрено! Места: {', '.join(assigned)}"
    if failed:
        result += f"\n⚠️ Уже заняты: {', '.join(failed)}"

    await callback.message.edit_text(
        msg_text + result,
        parse_mode="HTML",
    )

    # Notify user
    try:
        bot: Bot = callback.bot
        spots_text = ", ".join(assigned) if assigned else "не назначены"
        await bot.send_message(
            user_id,
            f"🎉 Ваша заявка одобрена!\n"
            f"Места: {spots_text}\n\n"
            f"Используйте меню для управления парковкой.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("approve_"))
async def approve_user(callback: CallbackQuery, db, is_moderator: bool, **kwargs):
    """Legacy single-spot approve (from /pending)."""
    if not is_moderator:
        await callback.answer("Только для модератора или администратора", show_alert=True)
        return

    parts = callback.data.split("_")
    user_id = int(parts[1])
    spot_number = int(parts[2]) if len(parts) > 2 else 0

    await db.set_user_status(user_id, "approved")

    if spot_number > 0:
        success = await db.add_spot(spot_number, user_id)
        if not success:
            await callback.message.edit_text(
                callback.message.text + "\n\n⚠️ Место уже занято! Пользователь одобрен, но место не назначено.",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ Одобрено!",
                parse_mode="HTML",
            )
    else:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Одобрено (без места).",
            parse_mode="HTML",
        )

    try:
        bot: Bot = callback.bot
        await bot.send_message(
            user_id,
            f"🎉 Ваша заявка одобрена!\n"
            f"Используйте меню для управления парковкой.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("reject_"))
async def reject_user(callback: CallbackQuery, db, is_moderator: bool, **kwargs):
    if not is_moderator:
        await callback.answer("Только для модератора или администратора", show_alert=True)
        return

    user_id = int(callback.data.split("_")[1])
    await db.set_user_status(user_id, "rejected")

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ Отклонено.",
        parse_mode="HTML",
    )

    try:
        bot: Bot = callback.bot
        await bot.send_message(user_id, "❌ Ваша заявка отклонена администратором.")
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.answer()


# === Admin commands ===

@router.message(Command("pending"))
async def cmd_pending(message: Message, db, is_moderator: bool, **kwargs):
    if not is_moderator:
        return

    pending = await db.get_users_by_status("pending")
    if not pending:
        await message.answer("Нет заявок на рассмотрение.")
        return

    for user in pending:
        await message.answer(
            f"📋 {user['name']}\n"
            f"Username: @{user['username'] or 'нет'}\n"
            f"ID: <code>{user['telegram_id']}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Одобрить (без места)",
                        callback_data=f"approve_{user['telegram_id']}_0",
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"reject_{user['telegram_id']}",
                    ),
                ]
            ]),
        )


@router.message(Command("users"))
async def cmd_users(message: Message, db, is_admin: bool, **kwargs):
    if not is_admin:
        return

    users = await db.get_all_users()
    if not users:
        await message.answer("Пользователей нет.")
        return

    lines = ["<b>Пользователи:</b>\n"]
    for u in users:
        spots = await db.get_user_spots(u["telegram_id"])
        spot_nums = ", ".join(str(s["spot_number"]) for s in spots) if spots else "—"
        status_icon = {
            "approved": "✅", "pending": "⏳", "rejected": "❌", "banned": "🚫"
        }.get(u["status"], "❓")
        lines.append(
            f"{status_icon} {u['name']} | Места: {spot_nums} | @{u['username'] or '—'}"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message, db, is_admin: bool, **kwargs):
    if not is_admin:
        return

    stats = await db.get_stats()
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"Пользователей: {stats['users_total']} (одобрено: {stats['users_approved']}, ожидают: {stats['users_pending']})\n"
        f"Мест занято: {stats['spots_total']} (свободно временно: {stats['spots_free']})\n"
        f"Сообщений: {stats['messages_total']}\n"
        f"Активных гостевых: {stats['guests_active']}",
        parse_mode="HTML",
    )


@router.message(Command("backup"))
async def cmd_backup(message: Message, db, is_admin: bool, **kwargs):
    if not is_admin:
        return

    data = await db.export_all_data()
    file = BufferedInputFile(
        data.encode("utf-8"), filename="parking_backup.json"
    )
    await message.answer_document(file, caption="📦 Полный бэкап базы данных")


@router.message(Command("restore"))
async def cmd_restore(message: Message, state: FSMContext, is_admin: bool, **kwargs):
    if not is_admin:
        return

    await message.answer("Отправьте JSON-файл бэкапа:")
    await state.set_state(BackupState.waiting_for_file)


@router.message(BackupState.waiting_for_file, F.document)
async def restore_file(message: Message, state: FSMContext, db, is_admin: bool, **kwargs):
    if not is_admin:
        return

    bot: Bot = message.bot
    file = await bot.download(message.document)
    json_str = file.read().decode("utf-8")

    try:
        counts = await db.import_all_data(json_str)
        await message.answer(
            f"✅ Импорт завершён:\n" +
            "\n".join(f"  {k}: {v}" for k, v in counts.items())
        )
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        await message.answer(f"❌ Ошибка импорта: {e}")

    await state.clear()


# === Ban/Unban via callbacks ===

@router.callback_query(F.data.startswith("ban_"))
async def ban_user(callback: CallbackQuery, db, is_admin: bool, **kwargs):
    if not is_admin:
        await callback.answer("Только для администратора", show_alert=True)
        return

    user_id = int(callback.data.split("_")[1])
    await db.set_user_status(user_id, "banned")
    await callback.message.edit_text(
        callback.message.text + "\n\n🚫 Заблокирован.",
        parse_mode="HTML",
    )
    await callback.answer()


# === Add spot (for approved users) ===

@router.message(F.text == MENU_BUTTONS["add_spot"])
async def add_spot_start(message: Message, state: FSMContext, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    await message.answer("Введите номер нового парковочного места:")
    await state.set_state(AddSpotState.waiting_for_spot)


@router.message(AddSpotState.waiting_for_spot)
async def add_spot_number(message: Message, state: FSMContext, db, is_moderator: bool, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)
    if spot_number < 1 or spot_number > 9999:
        await message.answer("Номер места должен быть от 1 до 9999:")
        return

    existing = await db.get_spot(spot_number)
    if existing:
        await message.answer(f"Место {spot_number} уже занято.")
        await state.clear()
        return

    if is_moderator:
        # Staff can add spots directly
        await db.add_spot(spot_number, message.from_user.id)
        spots = await db.get_user_spots(message.from_user.id)
        spots_text = ", ".join(str(s["spot_number"]) for s in spots)
        await message.answer(
            f"✅ Место {spot_number} добавлено!\nВаши места: {spots_text}"
        )
    else:
        # Regular user — needs staff approval
        bot: Bot = message.bot
        for admin_id in STAFF_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"📋 <b>Запрос на доп. место</b>\n\n"
                    f"Пользователь: {message.from_user.full_name}\n"
                    f"Место: {spot_number}\n"
                    f"ID: <code>{message.from_user.id}</code>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Одобрить",
                                callback_data=f"approve_{message.from_user.id}_{spot_number}",
                            ),
                            InlineKeyboardButton(
                                text="❌ Отклонить",
                                callback_data=f"reject_{message.from_user.id}",
                            ),
                        ]
                    ]),
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        await message.answer(
            f"Запрос на место {spot_number} отправлен администратору. Ожидайте."
        )

    await state.clear()


# === Remove spot (for approved users) ===

@router.message(F.text == MENU_BUTTONS["remove_spot"])
async def remove_spot_start(message: Message, state: FSMContext, db, is_approved: bool, **kwargs):
    if not is_approved:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    spots = await db.get_user_spots(message.from_user.id)
    if not spots:
        await message.answer("У вас нет зарегистрированных мест.")
        return

    spots_text = ", ".join(str(s["spot_number"]) for s in spots)
    await message.answer(
        f"Ваши места: {spots_text}\n\n"
        f"Введите номер места, которое хотите удалить:"
    )
    await state.set_state(RemoveSpotState.waiting_for_spot)


@router.message(RemoveSpotState.waiting_for_spot)
async def remove_spot_number(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число:")
        return

    spot_number = int(text)
    removed = await db.remove_spot(spot_number, message.from_user.id)

    if removed:
        spots = await db.get_user_spots(message.from_user.id)
        spots_text = ", ".join(str(s["spot_number"]) for s in spots) if spots else "нет мест"
        await message.answer(f"✅ Место {spot_number} удалено.\nВаши места: {spots_text}")
    else:
        await message.answer(f"Место {spot_number} не принадлежит вам.")

    await state.clear()


# === Admin: manage spots for any user ===

@router.message(Command("spot"))
async def cmd_admin_spot(message: Message, state: FSMContext, db, is_moderator: bool, **kwargs):
    """Staff command: /spot add 142 228501005 or /spot remove 142"""
    if not is_moderator:
        return

    parts = message.text.strip().split()
    # /spot add <number> <user_id> — assign spot to user
    # /spot remove <number> — free spot from whoever owns it
    # /spot — show help

    if len(parts) < 2:
        await message.answer(
            "🛡 <b>Управление местами</b>\n\n"
            "<code>/spot add НомерМеста UserID</code> — назначить место\n"
            "<code>/spot remove НомерМеста</code> — освободить место\n"
            "<code>/spot info НомерМеста</code> — инфо о месте",
            parse_mode="HTML",
        )
        return

    action = parts[1].lower()

    if action == "add" and len(parts) >= 4:
        spot_number = int(parts[2])
        user_id = int(parts[3])

        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"Пользователь {user_id} не найден.")
            return

        success = await db.add_spot(spot_number, user_id)
        if success:
            await message.answer(f"✅ Место {spot_number} назначено {user['name']} ({user_id})")
        else:
            await message.answer(f"⚠️ Место {spot_number} уже занято.")

    elif action == "remove" and len(parts) >= 3:
        spot_number = int(parts[2])
        spot = await db.get_spot(spot_number)
        if not spot:
            await message.answer(f"Место {spot_number} не зарегистрировано.")
            return

        await db.force_remove_spot(spot_number)
        await message.answer(f"✅ Место {spot_number} освобождено.")

    elif action == "info" and len(parts) >= 3:
        spot_number = int(parts[2])
        owner = await db.get_spot_owner(spot_number)
        if owner:
            await message.answer(
                f"Место {spot_number}: {owner['name']} (@{owner['username'] or '—'})\n"
                f"ID: <code>{owner['telegram_id']}</code>",
                parse_mode="HTML",
            )
        else:
            await message.answer(f"Место {spot_number} свободно.")

    else:
        await message.answer("Неверный формат. Используйте /spot для справки.")
