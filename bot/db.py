import sqlite3
import json
from config import DB_PATH
from datetime import datetime, timedelta, timezone
import logging


# ===== Инициализация базы =====
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Таблица пользователей
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        phone TEXT,
        fio TEXT,
        district TEXT,
        registered_at TEXT,
        salary REAL DEFAULT 0,
        bonus INTEGER DEFAULT 0
    )
    """)


    # Таблица адресов
    cur.execute("""
    CREATE TABLE IF NOT EXISTS addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT
    )
    """)

    # Таблица задач
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address_id INTEGER,
        title TEXT,
        description TEXT,
        safe_code TEXT DEFAULT '',
        comment TEXT,
        created_at TEXT
    )
    """)

    # Таблица назначений задач
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        task_id INTEGER,
        status TEXT,
        photo TEXT,
        video TEXT,
        missing_text TEXT
    )
    """)

    # Таблица выполненных задач
    cur.execute("""
    CREATE TABLE IF NOT EXISTS done_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        task_id INTEGER,
        description TEXT,
        photo TEXT,
        video TEXT,
        missing_text TEXT,
        address TEXT,
        completed_at TEXT,
        confirmed INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

    # после создания делаем миграцию
    migrate_done_tasks_table()


def migrate_done_tasks_table():
    """Добавляет недостающие колонки в done_tasks."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(done_tasks)")
    columns = [col[1] for col in cur.fetchall()]

    if "address" not in columns:
        cur.execute("ALTER TABLE done_tasks ADD COLUMN address TEXT")
    if "completed_at" not in columns:
        cur.execute("ALTER TABLE done_tasks ADD COLUMN completed_at TEXT")
    if "confirmed" not in columns:
        cur.execute("ALTER TABLE done_tasks ADD COLUMN confirmed INTEGER DEFAULT 0")

    conn.commit()
    conn.close()

def migrate_done_tasks_breakages():
    """Добавляет колонки для хранения фото/видео поломок в done_tasks."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(done_tasks)")
    columns = [col[1] for col in cur.fetchall()]

    if "breakage_photos" not in columns:
        cur.execute("ALTER TABLE done_tasks ADD COLUMN breakage_photos TEXT DEFAULT '[]'")
    if "breakage_videos" not in columns:
        cur.execute("ALTER TABLE done_tasks ADD COLUMN breakage_videos TEXT DEFAULT '[]'")

    conn.commit()
    conn.close()


# ===== Пользователи =====
def save_partial_contact(user_id: int, phone: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users(user_id, phone, registered_at) VALUES(?, ?, ?)",
        (user_id, phone, datetime.utcnow().isoformat())
    )
    cur.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
    conn.commit()
    conn.close()

def add_bonus(user_id: int, amount: int):
    """
    Начисляет бонус пользователю:
    - обновляет поле bonus в users
    - обновляет total_bonus в user_stats
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Обновляем основной бонус
    cur.execute("UPDATE users SET bonus = COALESCE(bonus, 0) + ? WHERE user_id = ?", (amount, user_id))

    # Обновляем статистику
    cur.execute("CREATE TABLE IF NOT EXISTS user_stats (user_id INTEGER PRIMARY KEY, total_salary INTEGER DEFAULT 0, total_bonus INTEGER DEFAULT 0)")
    cur.execute("INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)", (user_id,))
    cur.execute("UPDATE user_stats SET total_bonus = COALESCE(total_bonus, 0) + ? WHERE user_id = ?", (amount, user_id))

    conn.commit()
    conn.close()

def migrate_users_add_reg_date():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if "reg_date" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN reg_date TEXT")
    conn.commit()
    conn.close()

def get_all_monthly_tasks():
    """Возвращает список (fio, monthly_tasks) для всех пользователей."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT u.fio, COALESCE(s.monthly_tasks, 0)
        FROM users u
        LEFT JOIN user_stats s ON u.user_id = s.user_id
        ORDER BY s.monthly_tasks DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def save_full_profile(user_id: int, fio: str, district: str, reg_date: str = None):
    """Сохраняет полный профиль пользователя с актуальной датой регистрации (МСК)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Московское время
    MSK = timezone(timedelta(hours=3))
    reg_date = reg_date or datetime.now(MSK).isoformat()

    cur.execute("""
        UPDATE users
        SET fio = ?, district = ?, registered_at = ?
        WHERE user_id = ?
    """, (fio, district, reg_date, user_id))

    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT phone, fio, district, registered_at, salary, COALESCE(bonus, 0) 
        FROM users WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def is_registered(user_id: int) -> bool:
    row = get_user(user_id)
    return bool(row and row[0] and row[1])

def migrate_users_rank():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if "rank" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN rank TEXT DEFAULT 'novice'")
    conn.commit()
    conn.close()

def update_user_rank(user_id: int, rank: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank, user_id))
    conn.commit()
    conn.close()

def get_user_rank(user_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT rank FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "novice"

def migrate_users_add_rank():
    """Добавляем колонку rank в таблицу users, если её нет"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if "rank" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN rank TEXT DEFAULT 'novice'")
    conn.commit()
    conn.close()


def set_user_rank(user_id: int, rank: str):
    """Присваивает пользователю ранг"""
    migrate_users_add_rank()  # гарантируем, что колонка есть
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank, user_id))
    conn.commit()
    conn.close()


def get_user_rank(user_id: int) -> str:
    """Возвращает ранг пользователя"""
    migrate_users_add_rank()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT rank FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else "novice"


RANKS = {
    "novice": {"title": "Начинающая горничная", "salary": 400},
    "maid": {"title": "Горничная", "salary": 500},
    "admin": {"title": "Админ", "salary": 0},
    "dev": {"title": "Разработчик", "salary": 0}
}


# ===== Выполненные задачи =====
def save_done_task(
    user_id,
    task_id,
    description,
    photos,
    videos,
    missing_text,
    address,
    breakage_photos=None,
    breakage_videos=None,
    remaining_photos=None
):
    """
    Универсальная функция сохранения выполненной задачи.
    Теперь поддерживает: фото/видео, поломки и остатки.
    Автоматически добавляет недостающие колонки.
    """
    import sqlite3, json
    from datetime import datetime
    from bot.config import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- Проверяем наличие таблицы ---
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='done_tasks'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE done_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_id INTEGER,
                description TEXT,
                photos TEXT,
                videos TEXT,
                missing_text TEXT,
                address TEXT,
                completed_at TEXT,
                fio TEXT,
                breakage_photos TEXT,
                breakage_videos TEXT,
                remaining_photos TEXT,
                confirmed INTEGER DEFAULT 0
            )
        """)
        conn.commit()

    # --- Узнаём текущие колонки ---
    cur.execute("PRAGMA table_info(done_tasks)")
    existing_cols = [row[1] for row in cur.fetchall()]

    # --- Проверяем недостающие ---
    needed = {
        "photos": "TEXT",
        "videos": "TEXT",
        "breakage_photos": "TEXT",
        "breakage_videos": "TEXT",
        "remaining_photos": "TEXT",
        "description": "TEXT",
        "missing_text": "TEXT",
        "address": "TEXT",
        "completed_at": "TEXT",
        "fio": "TEXT",
        "task_id": "INTEGER",
        "confirmed": "INTEGER"
    }

    for col, col_type in needed.items():
        if col not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE done_tasks ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
    conn.commit()

    # --- Преобразуем поля ---
    photos_json = json.dumps(photos or [])
    videos_json = json.dumps(videos or [])
    breakage_photos_json = json.dumps(breakage_photos or [])
    breakage_videos_json = json.dumps(breakage_videos or [])
    remaining_photos_json = json.dumps(remaining_photos or [])
    completed_at = datetime.now().isoformat(timespec='seconds')

    # --- Получаем ФИО ---
    fio = None
    try:
        cur.execute("SELECT fio FROM users WHERE user_id = ?", (user_id,))
        r = cur.fetchone()
        fio = r[0] if r and r[0] else None
    except Exception:
        fio = None

    # --- Вставляем запись ---
    cur.execute("""
        INSERT INTO done_tasks (
            user_id, task_id, description, photos, videos,
            missing_text, address, completed_at, fio,
            breakage_photos, breakage_videos, remaining_photos
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        task_id,
        description,
        photos_json,
        videos_json,
        missing_text,
        address,
        completed_at,
        fio,
        breakage_photos_json,
        breakage_videos_json,
        remaining_photos_json
    ))

    print("✅ Сохранена задача в БД:")
    print("   breakage_photos =", breakage_photos)
    print("   remaining_photos =", remaining_photos)

    conn.commit()
    conn.close()


def migrate_done_tasks_fix_columns():
    """Создает недостающие колонки и исправляет старые записи"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Список нужных колонок с типами по умолчанию
    needed_cols = {
        "photos": "TEXT DEFAULT '[]'",
        "videos": "TEXT DEFAULT '[]'",
        "breakage_photos": "TEXT DEFAULT '[]'",
        "breakage_videos": "TEXT DEFAULT '[]'"
    }

    # Проверяем существующие колонки
    cur.execute("PRAGMA table_info(done_tasks)")
    existing_cols = [row[1] for row in cur.fetchall()]

    # Добавляем недостающие колонки
    for col, col_def in needed_cols.items():
        if col not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE done_tasks ADD COLUMN {col} {col_def}")
            except Exception as e:
                print(f"⚠️ Не удалось добавить колонку {col}: {e}")

    conn.commit()

    # Исправляем старые записи, где колонка пустая или NULL
    for col in needed_cols.keys():
        cur.execute(f"UPDATE done_tasks SET {col} = '[]' WHERE {col} IS NULL OR {col} = ''")

    conn.commit()
    conn.close()
    print("✅ done_tasks миграция завершена. Все колонки фото/видео исправлены.")


# ===== Функция для безопасного сохранения выполненной задачи =====
def save_done_task_safe(user_id, task_id, description, photos, videos, missing_text, address, breakage_photos=None, breakage_videos=None):
    """
    Универсальная функция сохранения выполненной задачи
    с гарантией наличия колонок и сохранением JSON
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- Проверяем и создаем таблицу, если нет ---
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='done_tasks'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE done_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_id INTEGER,
                description TEXT,
                photos TEXT DEFAULT '[]',
                videos TEXT DEFAULT '[]',
                missing_text TEXT,
                address TEXT,
                completed_at TEXT,
                fio TEXT,
                breakage_photos TEXT DEFAULT '[]',
                breakage_videos TEXT DEFAULT '[]',
                confirmed INTEGER DEFAULT 0
            )
        """)
        conn.commit()

    # --- Убеждаемся, что колонки есть ---
    migrate_done_tasks_fix_columns()

    # --- Подготавливаем JSON ---
    photos_json = json.dumps(photos or [])
    videos_json = json.dumps(videos or [])
    breakage_photos_json = json.dumps(breakage_photos or [])
    breakage_videos_json = json.dumps(breakage_videos or [])
    completed_at = datetime.now().isoformat(timespec='seconds')

    # Получаем FIO пользователя
    fio = None
    try:
        cur.execute("SELECT fio FROM users WHERE user_id = ?", (user_id,))
        r = cur.fetchone()
        fio = r[0] if r else None
    except Exception:
        fio = None

    # --- Сохраняем запись ---
    cur.execute("""
        INSERT INTO done_tasks (
            user_id, task_id, description, photos, videos,
            missing_text, address, completed_at, fio,
            breakage_photos, breakage_videos
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, task_id, description, photos_json, videos_json,
        missing_text, address, completed_at, fio,
        breakage_photos_json, breakage_videos_json
    ))

    conn.commit()
    conn.close()

def migrate_done_tasks_add_address_id():
    """
    Добавляет колонку address_id в done_tasks, если её нет.
    """
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(done_tasks)")
    existing = [r[1] for r in cur.fetchall()]
    if "address_id" not in existing:
        cur.execute("ALTER TABLE done_tasks ADD COLUMN address_id INTEGER")
        conn.commit()
    conn.close()

def migrate_done_tasks_add_addr_id():
    """Добавляет колонку addr_id в done_tasks, если её нет"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(done_tasks)")
    columns = [row[1] for row in cur.fetchall()]

    if "addr_id" not in columns:
        cur.execute("ALTER TABLE done_tasks ADD COLUMN addr_id INTEGER")
        conn.commit()
        print("✅ Колонка addr_id добавлена в done_tasks.")
    else:
        print("ℹ️ Колонка addr_id уже существует в done_tasks.")

    conn.close()


# ===== Квартиры (фото/видео) =====

def migrate_apartment_photos():
    """Создает таблицу apartment_photos если её нет"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS apartment_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address_id INTEGER,
            file_id TEXT,
            media_type TEXT CHECK(media_type IN ('photo','video')),
            comment TEXT,
            uploaded_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def add_apartment_media(address_id: int, file_id: str, media_type: str, comment: str = ""):
    """Добавить фото/видео к квартире"""
    migrate_apartment_photos()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO apartment_photos (address_id, file_id, media_type, comment, uploaded_at)
        VALUES (?, ?, ?, ?, ?)
    """, (address_id, file_id, media_type, comment, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_apartment_media(address_id: int):
    """Получить все фото/видео по квартире"""
    migrate_apartment_photos()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, file_id, media_type, comment, uploaded_at
        FROM apartment_photos
        WHERE address_id = ?
        ORDER BY uploaded_at ASC
    """, (address_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_apartment_media(media_id: int):
    """Удалить одну фотку/видео"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM apartment_photos WHERE id = ?", (media_id,))
    conn.commit()
    conn.close()


def clear_apartment_media(address_id: int):
    """Очистить все фото/видео у квартиры"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM apartment_photos WHERE address_id = ?", (address_id,))
    conn.commit()
    conn.close()



def get_done_task_details(done_task_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT dt.user_id,
               dt.address,
               (SELECT fio FROM users WHERE user_id = dt.user_id) as fio,
               dt.photos,
               dt.videos,
               dt.missing_text,
               dt.completed_at,
               dt.description,
               dt.breakage_photos,
               dt.breakage_videos
        FROM done_tasks dt
        WHERE dt.id = ?
    """, (done_task_id,))
    row = cur.fetchone()
    conn.close()

    if row:
        user_id, address, fio, photo_json, video_json, missing_text, completed_at, description, breakage_photos_json, breakage_videos_json = row
        photos = json.loads(photo_json or '[]')
        videos = json.loads(video_json or '[]')
        breakage_photos = json.loads(breakage_photos_json or '[]')
        breakage_videos = json.loads(breakage_videos_json or '[]')
        return user_id, address, fio, photos, videos, missing_text, completed_at, description, breakage_photos, breakage_videos
    return None


def get_done_tasks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT dt.id,
               dt.address,
               (SELECT fio FROM users WHERE user_id = dt.user_id) as fio,
               dt.completed_at
        FROM done_tasks dt
        ORDER BY dt.id DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_done_task(done_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM done_tasks WHERE id = ?", (done_id,))
    conn.commit()
    conn.close()


def delete_all_done_tasks_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM done_tasks")
    conn.commit()
    conn.close()


def get_all_users_with_salary():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT 
            u.user_id,
            u.fio,
            COALESCE(s.total_salary, 0) AS total_salary,
            COALESCE(s.total_bonus, 0) AS total_bonus,
            COALESCE(SUM(p.amount), 0) AS total_penalty
        FROM users u
        LEFT JOIN user_stats s ON u.user_id = s.user_id
        LEFT JOIN penalties p ON u.user_id = p.user_id
        GROUP BY u.user_id, u.fio, s.total_salary, s.total_bonus
        ORDER BY u.fio
    """)
    users = c.fetchall()
    conn.close()
    return users

def migrate_tasks_safe_code():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cur.fetchall()]
    if "safe_code" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN safe_code TEXT DEFAULT ''")
    conn.commit()
    conn.close()

# ===== Поиск пользователей =====
def search_users(query: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, fio, phone, district, registered_at
        FROM users
        WHERE fio LIKE ? OR phone LIKE ?
    """, (f"%{query}%", f"%{query}%"))
    rows = cur.fetchall()
    conn.close()
    return rows


# ===== Зарплата и бонусы =====
def get_user_stats(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_salary INTEGER DEFAULT 0,
            total_bonus INTEGER DEFAULT 0
        )
    """)
    cur.execute("SELECT total_salary, total_bonus FROM user_stats WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row
    return 0, 0


def update_salary(user_id: int = None, value: int = 0, set_absolute: bool = False):
    """
    Если set_absolute=True — устанавливает конкретное значение.
    Если False — добавляет/вычитает сумму (value может быть отрицательным).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        if user_id:
            # создаем запись, если ее нет
            cur.execute("INSERT OR IGNORE INTO user_stats (user_id, total_salary) VALUES (?, 0)", (user_id,))

            if set_absolute:
                cur.execute("UPDATE user_stats SET total_salary = ? WHERE user_id = ?", (value, user_id))
                logging.info(f"[update_salary] Установлено total_salary={value} ₽ для user_id={user_id}")
            else:
                cur.execute("UPDATE user_stats SET total_salary = total_salary + ? WHERE user_id = ?", (value, user_id))
                logging.info(f"[update_salary] Изменено total_salary на {value:+} ₽ для user_id={user_id}")
        else:
            # обновляем всем
            if set_absolute:
                cur.execute("UPDATE user_stats SET total_salary = ?", (value,))
                logging.info(f"[update_salary] Установлено total_salary={value} ₽ для всех пользователей")
            else:
                cur.execute("UPDATE user_stats SET total_salary = total_salary + ?", (value,))
                logging.info(f"[update_salary] Изменено total_salary на {value:+} ₽ для всех пользователей")

        conn.commit()

        # получаем новое значение для user_id (если указан)
        if user_id:
            total_salary, total_bonus = get_user_stats(user_id)
            logging.info(f"[update_salary] Новое значение: total_salary={total_salary} ₽, total_bonus={total_bonus} ₽ (user_id={user_id})")

        return True

    except Exception as e:
        logging.exception(f"[update_salary] Ошибка при обновлении зарплаты (user_id={user_id}, value={value}): {e}")
        return False

    finally:
        conn.close()

def create_penalties_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS penalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT,
            date TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

def update_bonus(user_id: int, delta: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO user_stats(user_id, total_bonus) VALUES(?, 0)", (user_id,))
    cur.execute("SELECT total_bonus FROM user_stats WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    current_bonus = row[0] if row else 0
    new_bonus = max(0, current_bonus + delta)
    cur.execute("UPDATE user_stats SET total_bonus = ? WHERE user_id = ?", (new_bonus, user_id))
    conn.commit()
    conn.close()



def migrate_users_add_username():
    """Добавляем колонку username, если её нет"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if "username" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN username TEXT DEFAULT ''")
    conn.commit()
    conn.close()

# ===== Все пользователи =====
def get_all_users():
    """Возвращает всех пользователей как список кортежей (user_id, fio, username)"""
    migrate_users_add_username()  # гарантируем, что колонка есть
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, fio, username FROM users ORDER BY fio")
    rows = cur.fetchall()
    conn.close()
    return rows


# ===== Задачи на подтверждение =====
def get_pending_done_tasks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, description,
               (SELECT fio FROM users WHERE user_id = done_tasks.user_id)
        FROM done_tasks
        WHERE confirmed = 0
        ORDER BY completed_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def confirm_done_task_db(done_task_id: int, salary_value: int = 100, bonus_value: int = 10):
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, task_id, description FROM done_tasks WHERE id = ?", (done_task_id,))
            row = cur.fetchone()
            if not row:
                return None
            user_id, task_id, description = row

            # Подтверждаем задачу
            cur.execute("UPDATE done_tasks SET confirmed = 1 WHERE id = ?", (done_task_id,))

            # Начисляем зарплату и бонус в одной транзакции
            cur.execute("INSERT OR IGNORE INTO user_stats(user_id, total_salary, total_bonus) VALUES(?, 0, 0)", (user_id,))
            cur.execute("SELECT total_salary, total_bonus FROM user_stats WHERE user_id = ?", (user_id,))
            current_salary, current_bonus = cur.fetchone()
            new_salary = current_salary + salary_value
            new_bonus = current_bonus + bonus_value
            cur.execute("UPDATE user_stats SET total_salary = ?, total_bonus = ? WHERE user_id = ?", (new_salary, new_bonus, user_id))

            conn.commit()
            return user_id, description, salary_value, bonus_value
    except sqlite3.OperationalError:
        return None


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

def update_tasks_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Проверяем существующие колонки
    cur.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cur.fetchall()]

    # Добавляем новые колонки, если их нет
    if "address_id" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN address_id INTEGER")
    if "title" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN title TEXT")

    conn.commit()
    conn.close()

def get_all_addresses():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM addresses ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def add_task_with_address(address_id, title, description, comment="", safe_code="", executor_id=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Убедимся, что колонка executor_id есть (безопасно — можно вызывать раньше)
    cur.execute("PRAGMA table_info(tasks)")
    cols = [r[1] for r in cur.fetchall()]
    if "executor_id" not in cols:
        cur.execute("ALTER TABLE tasks ADD COLUMN executor_id INTEGER")
    # Вставляем запись
    cur.execute("""
        INSERT INTO tasks (address_id, title, description, safe_code, comment, executor_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        address_id,
        title,
        description,
        safe_code,
        comment,
        executor_id,
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()

def add_simple_task(description: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT,
            created_at TEXT
        )
    """)
    cur.execute(
        "INSERT INTO tasks (description, created_at) VALUES (?, ?)",
        (description, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def migrate_tasks_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cur.fetchall()]

    # добавляем недостающие поля
    if "address_id" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN address_id INTEGER")
    if "title" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN title TEXT")
    if "description" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN description TEXT")
    if "comment" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN comment TEXT")
    if "safe_code" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN safe_code TEXT DEFAULT ''")
    if "executor_id" not in columns:
        cur.execute("ALTER TABLE tasks ADD COLUMN executor_id INTEGER")

    conn.commit()
    conn.close()

def delete_address(addr_id: int, cascade: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if cascade:
        cur.execute("DELETE FROM tasks WHERE address_id = ?", (addr_id,))
    cur.execute("DELETE FROM addresses WHERE id = ?", (addr_id,))
    conn.commit()
    conn.close()

def delete_all_addresses():
    """Удаляет все адреса"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM addresses")
    conn.commit()
    conn.close()

def get_addresses_with_tasks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT addresses.id, addresses.title
        FROM addresses
        JOIN tasks ON tasks.address_id = addresses.id
        ORDER BY addresses.id ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def remove_bonuses_for_all():
    """Обнуляет бонусы всем пользователям"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE user_stats SET total_bonus = 0")
    conn.commit()
    conn.close()


def get_tasks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            t.id, 
            t.title, 
            t.description, 
            t.safe_code, 
            t.comment,
            a.id AS address_id, 
            a.title AS address_title, 
            a.floor, 
            a.apartment,
            u.fio AS executor_fio,
            t.executor_id
        FROM tasks t
        LEFT JOIN addresses a ON t.address_id = a.id
        LEFT JOIN users u ON t.executor_id = u.user_id
        ORDER BY t.id ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_task(task_id: int):
    """Удалить одну невыполненную задачу"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def delete_all_tasks():
    """Удалить все невыполненные задачи"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()

def migrate_tasks_add_executor():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # проверяем, есть ли колонка executor_id
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    if "executor_id" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN executor_id INTEGER")
        conn.commit()
    conn.close()


def migrate_addresses_table():
    """
    Обновляет таблицу addresses:
    - добавляет колонки floor и apartment, если их нет,
    - удаляет дубликаты (оставляет запись с минимальным rowid),
    - создаёт уникальный индекс по (title, floor, apartment).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) Убедимся, что таблица адресов существует (на случай, если вызов раньше)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT
        )
    """)
    conn.commit()

    # 2) Добавляем колонки, если их нет
    cur.execute("PRAGMA table_info(addresses)")
    existing_cols = [row[1] for row in cur.fetchall()]

    if "floor" not in existing_cols:
        cur.execute("ALTER TABLE addresses ADD COLUMN floor TEXT DEFAULT ''")
    if "apartment" not in existing_cols:
        cur.execute("ALTER TABLE addresses ADD COLUMN apartment TEXT DEFAULT ''")
    conn.commit()

    # 3) Удаляем дубликаты (оставляем запись с минимальным rowid для каждой комбинации)
    #    Используем GROUP BY title, COALESCE(floor, ''), COALESCE(apartment, '') чтобы корректно работать с NULL/пустыми значениями.
    try:
        cur.execute("""
            DELETE FROM addresses
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM addresses
                GROUP BY title, COALESCE(floor, ''), COALESCE(apartment, '')
            )
        """)
        conn.commit()
    except Exception as e:
        # На всякий случай логируем, но продолжаем — удаление дубликатов не критично
        print("Warning during deduplicate addresses:", e)

    # 4) Пытаемся создать уникальный индекс. После очистки дубликатов это обычно безопасно.
    try:
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_address_unique ON addresses(title, floor, apartment)")
        conn.commit()
    except sqlite3.IntegrityError as e:
        # Если всё ещё есть конфликты — сообщаем, индекс не создастся.
        print("Could not create unique index on addresses(title, floor, apartment):", e)

    conn.close()

def get_address_by_title(title):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, floor, apartment FROM addresses WHERE title = ? LIMIT 1",
        (title,)
    )
    result = cur.fetchone()
    conn.close()
    return result

def get_address_by_id(address_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, title, floor, apartment FROM addresses WHERE id = ?", (address_id,))
    row = cur.fetchone()
    conn.close()
    return row  # (id, title, floor, apartment)


def add_task(description: str):
    # Добавляем на дефолтный адрес с id=1
    add_task_with_address(
        address_id=1,
        title=description,
        description=description,
        safe_code="",
        comment=""
    )
def add_address(title: str, floor: str = "", apartment: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Создаём таблицу с колонками floor и apartment, если её нет
    cur.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            floor TEXT,
            apartment TEXT
        )
    """)
    # Вставляем один раз
    cur.execute("INSERT INTO addresses(title, floor, apartment) VALUES(?, ?, ?)", (title, floor, apartment))
    conn.commit()
    conn.close()

def add_or_update_user(user_id, fio=None, username=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            fio TEXT,
            username TEXT
        )
    """)

    # Если передано ФИО → сохраняем его вместе с username
    if fio is not None:
        cur.execute("""
            INSERT INTO users (user_id, fio, username) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET fio = excluded.fio, username = excluded.username
        """, (user_id, fio, username))
    else:
        # Иначе обновляем ТОЛЬКО username, fio не трогаем
        cur.execute("""
            INSERT INTO users (user_id, username) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username))
    conn.commit()
    conn.close()

def ensure_username_column():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]
    if "username" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.commit()
    conn.close()

def delete_user(user_id: int):
    """Удаляет пользователя, не трогая его задачи."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Удаляем пользователя из основной таблицы
    cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # Удаляем статистику пользователя
    cur.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))

    # ⚠️ Не трогаем выполненные задачи!
    # cur.execute("DELETE FROM done_tasks WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()


def get_monthly_cleaning_stats():
    """Возвращает статистику уборок за текущий месяц: [(fio, count), ...]"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Московское время
    MSK = timezone(timedelta(hours=3))
    now = datetime.now(MSK)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    cur.execute("""
        SELECT u.fio, COUNT(d.id) as count
        FROM done_tasks d
        JOIN users u ON d.user_id = u.user_id
        WHERE d.completed_at >= ?
        GROUP BY u.fio
        ORDER BY count DESC
    """, (month_start.isoformat(),))

    rows = cur.fetchall()
    conn.close()
    return rows

def add_bonuses_for_all(amount: int):
    """Начисляет бонус всем пользователям (увеличивает total_bonus)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE user_stats
        SET total_bonus = COALESCE(total_bonus, 0) + ?
    """, (amount,))
    conn.commit()
    conn.close()

def get_user_rank(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT rank FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    print(f"[DEBUG] get_user_rank({user_id}) -> {row}")  # 👈 добавь это

    return row[0] if row else None

def add_bonus_to_user(user_id: int, amount: int):
    """Добавляет бонус конкретному пользователю."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Обновляем в users
    cur.execute("UPDATE users SET bonus = COALESCE(bonus, 0) + ? WHERE user_id = ?", (amount, user_id))

    # Обновляем в user_stats
    cur.execute("INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)", (user_id,))
    cur.execute("""
        UPDATE user_stats
        SET total_bonus = COALESCE(total_bonus, 0) + ?
        WHERE user_id = ?
    """, (amount, user_id))

    conn.commit()
    conn.close()

def init_driver_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS driver_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            task_name TEXT,
            safe_code TEXT,
            comment TEXT,
            executor_id INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS driver_done_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_name TEXT,
            address TEXT,
            completed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def add_driver_task(address, task_name, safe_code, comment, executor_id=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO driver_tasks (address, task_name, safe_code, comment, executor_id)
        VALUES (?, ?, ?, ?, ?)
    """, (address, task_name, safe_code, comment, executor_id))
    conn.commit()
    conn.close()


def get_driver_tasks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, address, task_name, safe_code, comment, executor_id
        FROM driver_tasks
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_driver_task_by_id(task_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, address, task_name, safe_code, comment, executor_id
        FROM driver_tasks WHERE id = ?
    """, (task_id,))
    row = cur.fetchone()
    conn.close()
    return row

def add_driver_task(task_name, address, safe_code, comment):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS driver_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT,
            address TEXT,
            safe_code TEXT,
            comment TEXT,
            executor_id INTEGER
        )
    """)
    cur.execute("""
        INSERT INTO driver_tasks (task_name, address, safe_code, comment)
        VALUES (?, ?, ?, ?)
    """, (task_name, address, safe_code, comment))
    conn.commit()
    conn.close()


def assign_driver_to_task(task_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE driver_tasks SET executor_id = ? WHERE id = ?", (user_id, task_id))
    conn.commit()
    conn.close()


def mark_driver_task_done(user_id, task_id, task_name, address):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO driver_done_tasks (user_id, task_name, address)
        VALUES (?, ?, ?)
    """, (user_id, task_name, address))
    cur.execute("DELETE FROM driver_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()