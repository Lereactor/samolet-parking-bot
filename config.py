import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Admin — единственный главный администратор
_admin_str = os.getenv("ADMIN_ID", "0")
ADMIN_ID: int = int(_admin_str) if _admin_str and _admin_str.strip().isdigit() else 0

# Rate limiting
RATE_LIMIT_MESSAGES = 10
RATE_LIMIT_PERIOD = 60  # seconds

# Bot version — bump to broadcast updated menu to all users on next deploy
BOT_VERSION = "2.3"

# Cancel button text (used in FSM dialogs)
CANCEL_TEXT = "❌ Отмена"

# Main menu buttons
MENU_BUTTONS = {
    "notify": "✉️ Сообщить А/М",
    "directory": "📋 Справочник мест",
    "my_spot": "📍 Моё место",
    "history": "📨 История сообщений",
    "find_free": "🔍 Найти свободное",
    "reminder": "⏰ Напомнить об оплате",
    "add_spot": "➕ Добавить место",
    "remove_spot": "➖ Удалить место",
    "report": "🚨 Пожаловаться",
    "contact_uk": "📞 Связь с УК",
    "help": "❓ Помощь",
}

# User statuses
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_BANNED = "banned"

# Message sources
SOURCE_GROUP = "group"
SOURCE_PRIVATE = "private"
SOURCE_NOTIFY = "notify"
SOURCE_REPORT = "report"
