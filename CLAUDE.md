# Parking Bot - Development Rules

## Architecture
- Python 3.11 + aiogram 3.x + asyncpg + PostgreSQL
- No SQLite — PostgreSQL only
- No AI/LLM — purely utility bot with buttons and commands
- Deployed on Render (new account), monitored by UptimeRobot

## Code Rules
- One Database instance — passed via middleware, not created in handlers
- Callback prefixes must not overlap
- FSM cleanup: always `await state.clear()` after use
- Middleware order: RateLimit → Access
- Router order: start → parking → guest → announcements → group (catch-all last)
- HTML formatting for Telegram messages
- Async everything — no blocking calls
- Parking spots are plain numbers (integers)

## Database
- PostgreSQL with asyncpg, connection pool (min 1, max 5)
- Automatic table creation on startup
- Backup/restore via JSON export (like school-bot)

## Environment Variables
- BOT_TOKEN — Telegram bot token
- ADMIN_ID — Admin Telegram ID
- DATABASE_URL — PostgreSQL connection string

## Project Structure
```
bot.py              — entry point
config.py           — constants
handlers/
  start.py          — registration, admin commands
  parking.py        — core parking features
  guest.py          — guest passes
  announcements.py  — admin broadcasts
  group.py          — group @mention handling
services/
  database.py       — PostgreSQL operations
middlewares/
  access.py         — permission checks
  rate_limit.py     — message throttling
```
