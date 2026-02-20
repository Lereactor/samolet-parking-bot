# Parking Bot Design — ЖК

## Problem
Residents of a housing complex need a way to contact parking spot owners (blocked exits, alarms, etc.) without knowing their phone numbers.

## Solution
Telegram bot that maps parking spot numbers to users, enabling anonymous messaging through the bot.

## Core Flow
1. User → `/start` → enters name + spot number → admin approves
2. In group: `@bot 142 вы перегородили выезд` → bot DMs owner of spot 142
3. In private: menu with quick actions (blocked, SOS, guest pass, etc.)

## Database Schema (PostgreSQL)

### users
| Column | Type | Notes |
|--------|------|-------|
| telegram_id | BIGINT PK | Telegram user ID |
| username | TEXT | @username |
| name | TEXT | Display name |
| status | TEXT | pending/approved/rejected/banned |
| created_at | TIMESTAMPTZ | |

### parking_spots
| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| spot_number | INTEGER UNIQUE | Parking spot number |
| user_id | BIGINT FK→users | Owner |
| is_temporary_free | BOOLEAN | "Уезжаю" flag |
| free_until | TIMESTAMPTZ | When owner returns |
| created_at | TIMESTAMPTZ | |

### messages
| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| from_user_id | BIGINT FK→users | Sender |
| to_spot | INTEGER | Target spot number |
| message_text | TEXT | Message content |
| reply_text | TEXT | Owner's reply |
| source | TEXT | group/private/blocked/sos |
| created_at | TIMESTAMPTZ | |

### guest_passes
| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| host_user_id | BIGINT FK→users | Resident who invited |
| guest_info | TEXT | Guest description |
| spot_number | INTEGER | Spot to use |
| expires_at | TIMESTAMPTZ | Pass expiry |
| is_active | BOOLEAN | |
| created_at | TIMESTAMPTZ | |

### announcements
| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| admin_id | BIGINT | Who sent |
| text | TEXT | Announcement text |
| created_at | TIMESTAMPTZ | |

## Features Detail

### 1. Registration
- `/start` → FSM: enter name → enter spot number
- Admin gets notification with approve/reject buttons
- One user can have multiple spots

### 2. Group @Mention
- Bot parses messages mentioning it in groups
- Extracts spot number (regex: digits after bot mention)
- Sends DM to spot owner with message text
- Replies in group: "Владелец места N уведомлён"

### 3. "Перегородили!" (Blocked)
- Button in main menu → enter blocking car's spot number
- Owner of that spot gets urgent alert
- Logged as message with source='blocked'

### 4. "Уезжаю" (Away)
- Toggle: mark spot as temporarily free
- Optional: set return time
- Others can see free spots list

### 5. Guest Pass
- Enter guest info + duration (hours)
- Bot confirms and sets expiry
- Auto-deactivates on expiry

### 6. SOS: Alarm
- Button → enter spot number → owner gets alert
- Source='sos' in messages table

### 7. Announcements
- Admin-only command
- Broadcast text to all approved users

### 8. Spot Directory
- "Справочник" button → enter spot number → shows if occupied/free
- Does NOT reveal owner identity

## Tech Stack
- Python 3.11 + aiogram 3.4.1
- PostgreSQL + asyncpg 0.29.0
- aiohttp 3.9.1 (health check)
- Render deployment + UptimeRobot monitoring
