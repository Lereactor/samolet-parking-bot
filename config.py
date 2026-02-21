import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Admin IDs — поддержка нескольких админов через запятую
# ADMIN_IDS=228501005,123456789 или старый ADMIN_ID=228501005
ADMIN_IDS: set[int] = set()
_admin_ids_str = os.getenv("ADMIN_IDS", "")
if _admin_ids_str:
    ADMIN_IDS = {int(x.strip()) for x in _admin_ids_str.split(",") if x.strip().isdigit()}
if not ADMIN_IDS:
    _single = os.getenv("ADMIN_ID", "0")
    if _single and _single != "0":
        ADMIN_IDS = {int(_single)}

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
    "add_spot": "➕ Добавить место",
    "remove_spot": "➖ Удалить место",
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
