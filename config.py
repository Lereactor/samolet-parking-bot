import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL")

# Rate limiting
RATE_LIMIT_MESSAGES = 10
RATE_LIMIT_PERIOD = 60  # seconds

# Main menu buttons
MENU_BUTTONS = {
    "blocked": "🚫 Перегородили!",
    "sos": "🚨 SOS Сигнализация",
    "away": "🚗 Уезжаю / Вернулся",
    "guest": "🎫 Гостевой пропуск",
    "directory": "📋 Справочник мест",
    "my_spot": "📍 Моё место",
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
SOURCE_BLOCKED = "blocked"
SOURCE_SOS = "sos"
