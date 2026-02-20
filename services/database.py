import json
import logging
from datetime import datetime, timezone

import asyncpg

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self, database_url: str):
        self.pool = await asyncpg.create_pool(
            database_url, min_size=1, max_size=5
        )
        await self._create_tables()
        logger.info("Database connected and tables created")

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")

    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    username TEXT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS parking_spots (
                    id SERIAL PRIMARY KEY,
                    spot_number INTEGER NOT NULL UNIQUE,
                    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
                    is_temporary_free BOOLEAN NOT NULL DEFAULT FALSE,
                    free_until TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    from_user_id BIGINT REFERENCES users(telegram_id),
                    to_spot INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    reply_text TEXT,
                    source TEXT NOT NULL DEFAULT 'private',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guest_passes (
                    id SERIAL PRIMARY KEY,
                    host_user_id BIGINT NOT NULL REFERENCES users(telegram_id),
                    guest_info TEXT NOT NULL,
                    spot_number INTEGER,
                    expires_at TIMESTAMPTZ NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id SERIAL PRIMARY KEY,
                    admin_id BIGINT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

    # === Users ===

    async def add_user(self, telegram_id: int, username: str, name: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO users (telegram_id, username, name)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (telegram_id) DO UPDATE
                   SET username = $2, name = $3""",
                telegram_id, username, name,
            )

    async def get_user(self, telegram_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", telegram_id
            )

    async def set_user_status(self, telegram_id: int, status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET status = $1 WHERE telegram_id = $2",
                status, telegram_id,
            )

    async def get_users_by_status(self, status: str):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM users WHERE status = $1 ORDER BY created_at", status
            )

    async def get_all_approved_users(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM users WHERE status = 'approved' ORDER BY created_at"
            )

    async def get_all_users(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM users ORDER BY created_at")

    # === Parking Spots ===

    async def add_spot(self, spot_number: int, user_id: int) -> bool:
        """Assign spot to user. Returns False if spot already taken."""
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM parking_spots WHERE spot_number = $1", spot_number
            )
            if existing:
                return False
            await conn.execute(
                """INSERT INTO parking_spots (spot_number, user_id)
                   VALUES ($1, $2)""",
                spot_number, user_id,
            )
            return True

    async def get_spot(self, spot_number: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM parking_spots WHERE spot_number = $1", spot_number
            )

    async def get_spot_owner(self, spot_number: int):
        """Get the user who owns a spot."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """SELECT u.* FROM users u
                   JOIN parking_spots ps ON u.telegram_id = ps.user_id
                   WHERE ps.spot_number = $1""",
                spot_number,
            )

    async def get_user_spots(self, user_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """SELECT * FROM parking_spots WHERE user_id = $1
                   ORDER BY spot_number""",
                user_id,
            )

    async def remove_spot(self, spot_number: int, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM parking_spots WHERE spot_number = $1 AND user_id = $2",
                spot_number, user_id,
            )
            return result != "DELETE 0"

    async def set_spot_free(
        self, spot_number: int, is_free: bool, free_until=None
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE parking_spots
                   SET is_temporary_free = $1, free_until = $2
                   WHERE spot_number = $3""",
                is_free, free_until, spot_number,
            )

    async def get_free_spots(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """SELECT ps.*, u.name FROM parking_spots ps
                   JOIN users u ON ps.user_id = u.telegram_id
                   WHERE ps.is_temporary_free = TRUE
                   ORDER BY ps.spot_number"""
            )

    async def get_all_spots(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """SELECT ps.*, u.name, u.username FROM parking_spots ps
                   JOIN users u ON ps.user_id = u.telegram_id
                   ORDER BY ps.spot_number"""
            )

    # === Messages ===

    async def add_message(
        self, from_user_id: int, to_spot: int, message_text: str, source: str
    ) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO messages (from_user_id, to_spot, message_text, source)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                from_user_id, to_spot, message_text, source,
            )
            return row["id"]

    async def set_message_reply(self, message_id: int, reply_text: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE messages SET reply_text = $1 WHERE id = $2",
                reply_text, message_id,
            )

    async def get_messages_for_spot(self, spot_number: int, limit: int = 10):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """SELECT m.*, u.name as from_name FROM messages m
                   LEFT JOIN users u ON m.from_user_id = u.telegram_id
                   WHERE m.to_spot = $1
                   ORDER BY m.created_at DESC LIMIT $2""",
                spot_number, limit,
            )

    # === Guest Passes ===

    async def add_guest_pass(
        self, host_user_id: int, guest_info: str, spot_number: int, expires_at
    ) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO guest_passes (host_user_id, guest_info, spot_number, expires_at)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                host_user_id, guest_info, spot_number, expires_at,
            )
            return row["id"]

    async def get_active_guest_passes(self, host_user_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """SELECT * FROM guest_passes
                   WHERE host_user_id = $1 AND is_active = TRUE
                   AND expires_at > NOW()
                   ORDER BY expires_at""",
                host_user_id,
            )

    async def deactivate_expired_passes(self) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE guest_passes SET is_active = FALSE
                   WHERE is_active = TRUE AND expires_at <= NOW()"""
            )
            count = int(result.split()[-1])
            return count

    # === Announcements ===

    async def add_announcement(self, admin_id: int, text: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO announcements (admin_id, text)
                   VALUES ($1, $2) RETURNING id""",
                admin_id, text,
            )
            return row["id"]

    async def get_recent_announcements(self, limit: int = 5):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM announcements ORDER BY created_at DESC LIMIT $1",
                limit,
            )

    # === Stats ===

    async def get_stats(self) -> dict:
        async with self.pool.acquire() as conn:
            users_total = await conn.fetchval("SELECT COUNT(*) FROM users")
            users_approved = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE status = 'approved'"
            )
            users_pending = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE status = 'pending'"
            )
            spots_total = await conn.fetchval("SELECT COUNT(*) FROM parking_spots")
            spots_free = await conn.fetchval(
                "SELECT COUNT(*) FROM parking_spots WHERE is_temporary_free = TRUE"
            )
            messages_total = await conn.fetchval("SELECT COUNT(*) FROM messages")
            guests_active = await conn.fetchval(
                """SELECT COUNT(*) FROM guest_passes
                   WHERE is_active = TRUE AND expires_at > NOW()"""
            )
            return {
                "users_total": users_total,
                "users_approved": users_approved,
                "users_pending": users_pending,
                "spots_total": spots_total,
                "spots_free": spots_free,
                "messages_total": messages_total,
                "guests_active": guests_active,
            }

    # === Backup / Restore ===

    async def export_all_data(self) -> str:
        async with self.pool.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users")
            spots = await conn.fetch("SELECT * FROM parking_spots")
            messages = await conn.fetch("SELECT * FROM messages")
            guests = await conn.fetch("SELECT * FROM guest_passes")
            announcements = await conn.fetch("SELECT * FROM announcements")

        def serialize(rows):
            result = []
            for row in rows:
                item = dict(row)
                for key, value in item.items():
                    if isinstance(value, datetime):
                        item[key] = value.isoformat()
                result.append(item)
            return result

        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "users": serialize(users),
            "parking_spots": serialize(spots),
            "messages": serialize(messages),
            "guest_passes": serialize(guests),
            "announcements": serialize(announcements),
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    async def import_all_data(self, json_str: str) -> dict:
        data = json.loads(json_str)
        counts = {}
        async with self.pool.acquire() as conn:
            # Users
            for u in data.get("users", []):
                await conn.execute(
                    """INSERT INTO users (telegram_id, username, name, status, created_at)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (telegram_id) DO UPDATE
                       SET username = $2, name = $3, status = $4""",
                    u["telegram_id"], u.get("username"), u["name"],
                    u["status"], u["created_at"],
                )
            counts["users"] = len(data.get("users", []))

            # Spots
            for s in data.get("parking_spots", []):
                await conn.execute(
                    """INSERT INTO parking_spots (spot_number, user_id, is_temporary_free, free_until, created_at)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (spot_number) DO UPDATE
                       SET user_id = $2, is_temporary_free = $3, free_until = $4""",
                    s["spot_number"], s["user_id"], s["is_temporary_free"],
                    s.get("free_until"), s["created_at"],
                )
            counts["parking_spots"] = len(data.get("parking_spots", []))

            # Messages
            for m in data.get("messages", []):
                await conn.execute(
                    """INSERT INTO messages (from_user_id, to_spot, message_text, reply_text, source, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6)
                       ON CONFLICT DO NOTHING""",
                    m.get("from_user_id"), m["to_spot"], m["message_text"],
                    m.get("reply_text"), m["source"], m["created_at"],
                )
            counts["messages"] = len(data.get("messages", []))

            # Guest passes
            for g in data.get("guest_passes", []):
                await conn.execute(
                    """INSERT INTO guest_passes (host_user_id, guest_info, spot_number, expires_at, is_active, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6)
                       ON CONFLICT DO NOTHING""",
                    g["host_user_id"], g["guest_info"], g.get("spot_number"),
                    g["expires_at"], g["is_active"], g["created_at"],
                )
            counts["guest_passes"] = len(data.get("guest_passes", []))

            # Announcements
            for a in data.get("announcements", []):
                await conn.execute(
                    """INSERT INTO announcements (admin_id, text, created_at)
                       VALUES ($1, $2, $3)
                       ON CONFLICT DO NOTHING""",
                    a["admin_id"], a["text"], a["created_at"],
                )
            counts["announcements"] = len(data.get("announcements", []))

        return counts
