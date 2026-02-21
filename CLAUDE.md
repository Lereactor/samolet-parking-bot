# Parking Bot - Development Rules & Infrastructure

## Architecture
- Python 3.11 + aiogram 3.x + asyncpg + PostgreSQL
- No SQLite — PostgreSQL only
- No AI/LLM — purely utility bot with buttons and commands
- Parking spots are plain numbers (integers)
- Users can have multiple spots
- Admin is also a regular user (with auto-approve)

## Code Rules
- One Database instance — passed via middleware, not created in handlers
- Callback prefixes must not overlap (`approvemulti_`, `approve_`, `reject_`, `ban_`)
- FSM cleanup: always `await state.clear()` after use
- Middleware order: RateLimit → Access
- Router order: start → parking → guest → announcements → group (catch-all last)
- HTML formatting for Telegram messages
- Async everything — no blocking calls

## Project Structure
```
bot.py              — entry point, polling, health check :10000, auto-backup
config.py           — constants, menu buttons, statuses
handlers/
  start.py          — /start registration (multi-spot), admin commands, add/remove spot
  parking.py        — blocked, SOS, away/back, directory, my_spot, help
  guest.py          — guest passes (up to 72h)
  announcements.py  — /announce broadcast to all
  group.py          — group @mention → DM to spot owner
services/
  database.py       — PostgreSQL: 5 tables, CRUD, backup/restore, stats
middlewares/
  access.py         — user status + admin check, injects db/is_admin/is_approved
  rate_limit.py     — 10 msg/60s per user
docs/plans/         — design documents
```

## Database
- PostgreSQL with asyncpg, connection pool (min 1, max 5)
- Automatic table creation on startup
- Backup/restore via JSON export (like school-bot)
- Auto-backup to admin every 30 days
- Hourly cleanup of expired guest passes

### Tables
- **users** — telegram_id (PK), username, name, status, created_at
- **parking_spots** — spot_number (UNIQUE int), user_id (FK), is_temporary_free, free_until
- **messages** — from_user_id, to_spot, message_text, reply_text, source (group/private/blocked/sos)
- **guest_passes** — host_user_id, guest_info, spot_number, expires_at, is_active
- **announcements** — admin_id, text, created_at

## Environment Variables
- `BOT_TOKEN` — Telegram bot token
- `ADMIN_ID` — Admin Telegram ID (228501005)
- `DATABASE_URL` — PostgreSQL internal connection string

---

## Infrastructure & Pipeline

### Services Map
```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   GitHub          │────▶│   Render          │────▶│   Telegram API   │
│   Lereactor/      │     │   Web Service     │     │                  │
│   samolet-        │     │   (Oregon, free)  │     │   @Samolet_      │
│   parking-bot     │     │                   │     │   parking_bot    │
└──────────────────┘     │   python bot.py   │     └──────────────────┘
                          │   :10000 health   │
                          └────────┬──────────┘
                                   │
                          ┌────────▼──────────┐     ┌──────────────────┐
                          │   Render           │     │   UptimeRobot    │
                          │   PostgreSQL       │     │   /health ping   │
                          │   (Oregon, free)   │     │   every 5 min    │
                          └──────────────────┘     └──────────────────┘
```

### Accounts & Credentials
| Сервис | Аккаунт | Что хранится |
|--------|---------|-------------|
| GitHub | github.com/Lereactor | Репо `samolet-parking-bot` (private) |
| Render | lev@alaev.ru (team "My place") | Web Service + PostgreSQL (оба Oregon, free tier) |
| Telegram | @Samolet_parking_bot | Бот, токен в Render env vars |
| UptimeRobot | dashboard.uptimerobot.com | HTTP monitor → /health каждые 5 мин |

### Deploy Pipeline
```
git push origin main
        │
        ▼
Render autodeploy (или ручной trigger через API)
        │
        ▼
pip install -r requirements.txt
        │
        ▼
python bot.py
   ├── DB connect + auto-create tables
   ├── Health check server :10000
   ├── Auto-backup task (30 дней)
   ├── Cleanup task (expired passes, 1 час)
   └── Telegram polling loop
```

### Render API (для управления без дашборда)
```bash
# API Key
RENDER_KEY="rnd_5TTjjUWWEeWiTRenZJEFV5fhiHgb"

# Trigger deploy
curl -X POST -H "Authorization: Bearer $RENDER_KEY" \
  https://api.render.com/v1/services/srv-d6cep4ntn9qs73c7nkm0/deploys

# Check deploy status
curl -H "Authorization: Bearer $RENDER_KEY" \
  https://api.render.com/v1/services/srv-d6cep4ntn9qs73c7nkm0/deploys?limit=1

# Update env vars
curl -X PUT -H "Authorization: Bearer $RENDER_KEY" \
  -H "Content-Type: application/json" \
  -d '[{"key":"KEY","value":"VALUE"}]' \
  https://api.render.com/v1/services/srv-d6cep4ntn9qs73c7nkm0/env-vars

# Service ID: srv-d6cep4ntn9qs73c7nkm0
# DB ID: dpg-d6cejlgeumvs73ba20d0-a
# Owner ID: tea-d6cegk95pdvs73d376gg
```

### Bot User Flow
```
Новый пользователь                        Группа ЖК
       │                                       │
  /start → имя → места → "готово"         @bot 142 текст
       │                                       │
  Заявка → Админ одобряет              Парсинг номера места
       │                                       │
  Меню с кнопками                       DM владельцу места
       │                                       │
  ┌────┴─────────────────────┐          "Владелец уведомлён"
  │ Перегородили │ SOS       │
  │ Уезжаю      │ Гости     │
  │ Справочник  │ Моё место │
  │ + Место     │ - Место   │
  │ Помощь                   │
  └──────────────────────────┘
```

### Важные нюансы
- Render free tier засыпает через 15 мин без трафика → UptimeRobot пингует /health
- БД и сервис ОБЯЗАТЕЛЬНО в одном регионе (оба Oregon), иначе internal URL не работает
- Free PostgreSQL на Render живёт 90 дней (expires 2026-03-22), потом нужно пересоздать или перейти на paid
- Autodeploy может не срабатывать — если нужно быстро, trigger через API
- При добавлении env vars через API создания сервиса они могут не подхватиться — лучше PUT отдельным запросом
