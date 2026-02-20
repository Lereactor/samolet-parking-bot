# Session Log — Parking Bot

## 2026-02-21 — Project Kickoff

### Context
- New Telegram bot for ЖК (residential complex) parking management
- Based on same stack as school-bot (/telegram/)
- Same GitHub org, same monitoring (UptimeRobot), new Render account

### Design Decisions
- PostgreSQL only (with backup/restore like school-bot)
- Parking spots are plain numbers (integers)
- No AI/LLM — utility bot with buttons and commands
- Bot works in private chats AND groups

### Features (MVP)
1. **Core**: Register spot, notify owner via @mention in group
2. **Перегородили**: Quick alert to blocking car's owner
3. **Уезжаю**: Mark spot as temporarily free
4. **Гостевой пропуск**: Register guest for N hours
5. **SOS сигнализация**: Alert spot owner about alarm
6. **Объявления**: Admin broadcasts to all users
7. **Справочник мест**: Check if spot is occupied (no personal data)

### Pipeline
- [x] Task 1: Project structure and git
- [x] Task 2: config.py + database service
- [x] Task 3: Middlewares (access + rate_limit)
- [x] Task 4: Start handler (registration + admin)
- [x] Task 5: Parking handler (core features)
- [x] Task 6: Group handler (@mentions)
- [x] Task 7: Guest passes + announcements
- [x] Task 8: bot.py entry point
- [x] Task 9: Syntax check — all files compile clean

### Files Created
```
bot.py                      — entry point, polling, health check, auto-backup
config.py                   — constants, menu buttons
requirements.txt            — aiogram, asyncpg, aiohttp, python-dotenv
.env.example                — template for env vars
.gitignore                  — excludes .env, __pycache__, logs
CLAUDE.md                   — development rules
handlers/start.py           — /start registration, admin commands, backup/restore
handlers/parking.py         — blocked, SOS, away/back, directory, my_spot, help
handlers/guest.py           — guest pass workflow
handlers/announcements.py   — admin broadcast
handlers/group.py           — group @mention → DM to spot owner
services/database.py        — PostgreSQL: 5 tables, CRUD, backup/restore, stats
middlewares/access.py        — user status + admin check
middlewares/rate_limit.py    — 10 msg/60s per user
docs/plans/                 — design document
```

### Database Schema
- **users**: telegram_id, username, name, status, created_at
- **parking_spots**: spot_number (unique int), user_id, is_temporary_free, free_until
- **messages**: from_user_id, to_spot, message_text, reply_text, source
- **guest_passes**: host_user_id, guest_info, spot_number, expires_at, is_active
- **announcements**: admin_id, text, created_at

### Next Steps
- Create Telegram bot via @BotFather
- Set up PostgreSQL on Render (new account)
- Deploy to Render
- Add bot to ЖК group
- Set up UptimeRobot monitoring
