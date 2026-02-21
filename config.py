import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Admin — единственный главный администратор
_admin_str = os.getenv("ADMIN_ID", "0")
ADMIN_ID: int = int(_admin_str) if _admin_str and _admin_str.strip().isdigit() else 0

# Moderators — могут принимать заявки, объявления, управлять местами
MODERATOR_IDS: set[int] = set()
_mod_ids_str = os.getenv("MODERATOR_IDS", "")
if _mod_ids_str:
    MODERATOR_IDS = {int(x.strip()) for x in _mod_ids_str.split(",") if x.strip().isdigit()}

# Staff = admin + moderators (для общих проверок)
STAFF_IDS: set[int] = ({ADMIN_ID} if ADMIN_ID else set()) | MODERATOR_IDS

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
    "contact_uk": "📞 Связь с УК",
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
