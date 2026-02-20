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

from config import ADMIN_ID, MENU_BUTTONS

logger = logging.getLogger(__name__)
router = Router()


class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_spot = State()


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
            [KeyboardButton(text=MENU_BUTTONS["help"])],
        ],
        resize_keyboard=True,
    )


# === /start ===

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db, is_admin: bool, user_status: str, **kwargs):
    await state.clear()

    if is_admin and user_status == "new":
        await db.add_user(message.from_user.id, message.from_user.username, "Админ")
        await db.set_user_status(message.from_user.id, "approved")
        await message.answer(
            "👑 Вы зарегистрированы как администратор.\n\n"
            "Команды:\n"
            "/pending — заявки на одобрение\n"
            "/users — все пользователи\n"
            "/stats — статистика\n"
            "/announce — объявление\n"
            "/backup — экспорт БД\n"
            "/restore — импорт БД",
            reply_markup=main_menu_keyboard(),
        )
        return

    if user_status == "approved":
        await message.answer(
            "Вы уже зарегистрированы! Используйте меню ниже.",
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

    await state.update_data(name=name)
    await message.answer(
        f"Отлично, {name}! Теперь введите номер вашего парковочного места (число):"
    )
    await state.set_state(RegistrationState.waiting_for_spot)


@router.message(RegistrationState.waiting_for_spot)
async def registration_spot(message: Message, state: FSMContext, db, **kwargs):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите номер места как число (например: 142):")
        return

    spot_number = int(text)
    if spot_number < 1 or spot_number > 9999:
        await message.answer("Номер места должен быть от 1 до 9999:")
        return

    data = await state.get_data()
    name = data["name"]

    # Check if spot is already taken
    existing = await db.get_spot(spot_number)
    if existing:
        await message.answer(
            f"Место {spot_number} уже зарегистрировано за другим пользователем.\n"
            "Введите другой номер или обратитесь к администратору:"
        )
        return

    # Save user and spot request
    await db.add_user(
        message.from_user.id, message.from_user.username, name
    )
    await state.update_data(spot_number=spot_number)
    await state.clear()

    await message.answer(
        f"✅ Заявка отправлена!\n\n"
        f"Имя: {name}\n"
        f"Место: {spot_number}\n\n"
        f"Ожидайте одобрения администратором."
    )

    # Notify admin
    bot: Bot = message.bot
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📋 <b>Новая заявка</b>\n\n"
            f"Имя: {name}\n"
            f"Место: {spot_number}\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
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
        logger.error(f"Failed to notify admin: {e}")


# === Admin: approve/reject ===

@router.callback_query(F.data.startswith("approve_"))
async def approve_user(callback: CallbackQuery, db, is_admin: bool, **kwargs):
    if not is_admin:
        await callback.answer("Только для администратора", show_alert=True)
        return

    parts = callback.data.split("_")
    user_id = int(parts[1])
    spot_number = int(parts[2])

    await db.set_user_status(user_id, "approved")
    success = await db.add_spot(spot_number, user_id)

    if not success:
        # Spot was taken in the meantime
        await callback.message.edit_text(
            callback.message.text + "\n\n⚠️ Место уже занято! Пользователь одобрен, но место не назначено.",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Одобрено!",
            parse_mode="HTML",
        )

    # Notify user
    try:
        bot: Bot = callback.bot
        await bot.send_message(
            user_id,
            f"🎉 Ваша заявка одобрена!\n"
            f"Место {spot_number} закреплено за вами.\n\n"
            f"Используйте меню для управления парковкой.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("reject_"))
async def reject_user(callback: CallbackQuery, db, is_admin: bool, **kwargs):
    if not is_admin:
        await callback.answer("Только для администратора", show_alert=True)
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
async def cmd_pending(message: Message, db, is_admin: bool, **kwargs):
    if not is_admin:
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
