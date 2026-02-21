import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, DATABASE_URL
from services.database import Database
from middlewares.rate_limit import RateLimitMiddleware
from middlewares.access import AccessMiddleware
from handlers import start, parking, guest, announcements, group

# === Logging ===

logger = logging.getLogger(__name__)

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


# === Health check ===

async def health_handler(request):
    return web.Response(text="OK")


async def run_web_server():
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)

    port = int(os.getenv("PORT", "10000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server on port {port}")
    return runner


# === Auto-backup ===

async def auto_backup_loop(bot: Bot, db: Database):
    """Export full DB every 30 days and send to admin."""
    from config import ADMIN_ID
    from aiogram.types import BufferedInputFile

    while True:
        await asyncio.sleep(30 * 24 * 60 * 60)  # 30 days
        if not ADMIN_ID:
            continue
        try:
            data = await db.export_all_data()
            file = BufferedInputFile(
                data.encode("utf-8"), filename="parking_auto_backup.json"
            )
            try:
                await bot.send_document(ADMIN_ID, file, caption="📦 Автоматический бэкап (30 дней)")
            except Exception as e:
                logger.error(f"Auto-backup to {ADMIN_ID} failed: {e}")
            logger.info("Auto-backup sent to admin")
        except Exception as e:
            logger.error(f"Auto-backup failed: {e}")


# === Expired passes cleanup ===

async def cleanup_loop(db: Database):
    """Deactivate expired guest passes and reset free spots."""
    while True:
        await asyncio.sleep(60 * 60)  # Every hour
        try:
            expired = await db.deactivate_expired_passes()
            if expired > 0:
                logger.info(f"Deactivated {expired} expired guest passes")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


# === Main ===

async def main():
    setup_logging()
    logger.info("Starting Parking Bot...")

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return

    if not DATABASE_URL:
        logger.error("DATABASE_URL not set")
        return

    # Database
    db = Database()
    await db.connect(DATABASE_URL)

    # Bot & dispatcher
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()

    # Middlewares (order matters: rate_limit first, then access)
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(AccessMiddleware(db))
    dp.callback_query.middleware(AccessMiddleware(db))

    # Routers (order matters: specific first, catch-all last)
    dp.include_router(start.router)
    dp.include_router(parking.router)
    dp.include_router(guest.router)
    dp.include_router(announcements.router)
    dp.include_router(group.router)  # Group handler last (catch-all for groups)

    # Web server for health checks
    web_runner = await run_web_server()

    # Background tasks
    asyncio.create_task(auto_backup_loop(bot, db))
    asyncio.create_task(cleanup_loop(db))

    logger.info("Bot is running!")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        await web_runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
