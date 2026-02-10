import asyncio
import os
import logging
import logging.handlers
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from bot import dev
from handlers import meneger
import sqlite3
from bot.config import DB_PATH
from handlers.driver_warehouse import router as driver_router
from bot.handlers import driver_tasks
from bot.db import init_driver_tables


from config import API_TOKEN
from db import (
    init_db,
    update_tasks_table,
    migrate_tasks_safe_code,
    migrate_addresses_table,
    migrate_tasks_add_executor,
    migrate_users_add_reg_date,
    migrate_done_tasks_breakages,
    migrate_done_tasks_add_address_id,
    migrate_done_tasks_add_addr_id,
    create_penalties_table
)
from handlers import registration, admin, tasks, profile
from db import migrate_done_tasks_fix_columns, save_done_task_safe

import time

# === Очистка логов раз в неделю ===
LOG_FILE = "bot.log"
LOG_LIFETIME_DAYS = 7  # через сколько дней очищать лог

def clear_old_log():
    if os.path.exists(LOG_FILE):
        mtime = os.path.getmtime(LOG_FILE)
        file_age_days = (time.time() - mtime) / (60 * 60 * 24)
        if file_age_days > LOG_LIFETIME_DAYS:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("")  # очищаем лог
            print("🧹 Лог-файл очищен (старше 7 дней)")


# ===== Настройка логирования =====
formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Вывод в консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Ротирующий файл
file_handler = logging.handlers.RotatingFileHandler(
    "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)

# Применяем ко всем логгерам
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.handlers = []  # очищаем дефолтные обработчики
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)


# ===== Миграции БД =====
init_db()
logging.info(f"База данных инициализирована: {os.path.abspath(DB_PATH)}")
migrate_tasks_safe_code()
migrate_users_add_reg_date()
migrate_done_tasks_add_address_id()
migrate_addresses_table()
migrate_tasks_add_executor()
migrate_done_tasks_breakages()
migrate_done_tasks_add_addr_id()
create_penalties_table()
update_tasks_table()

# 🔹 Новая миграция для исправления колонок photos/videos
migrate_done_tasks_fix_columns()
logging.info("Миграция done_tasks для фото/видео завершена")
# ===== Создание таблицы settings (если нет) =====
def init_settings():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()
    logging.info("✅ Таблица settings инициализирована (если отсутствовала).")

init_settings()



# ===== Мидлварь для логирования ошибок =====
class ErrorLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except Exception:
            logging.getLogger(__name__).exception(f"Ошибка при обработке события: {event}")
            raise

init_driver_tables()

async def main():
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем роутеры
    dp.include_router(registration.router)
    dp.include_router(admin.router)
    dp.include_router(tasks.router)
    dp.include_router(profile.router)
    dp.include_router(dev.dev_router)
    dp.include_router(meneger.router)
    dp.include_router(driver_router)
    dp.include_router(driver_tasks.router)

    # Подключаем мидлвари
    dp.message.middleware(ErrorLoggingMiddleware())
    dp.callback_query.middleware(ErrorLoggingMiddleware())

    logging.info("Бот запущен, начинаем polling...")

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.exception(f"Произошла ошибка при polling: {e}")
    finally:
        await bot.session.close()
        logging.info("Бот остановлен")



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную")



