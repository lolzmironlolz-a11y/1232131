from aiogram import Router, types, F
from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from bot.states import TaskCreate, TaskWork
from bot.db import get_user_rank
from bot.ranks import RANKS
from bot.db import add_task_with_address as add_task, get_tasks, save_done_task, get_user
from bot.keyboards import main_kb
from aiogram_media_group import media_group_handler
import sqlite3
from bot.db import add_simple_task
from bot.db import add_task_with_address
from aiogram_media_group import media_group_handler
from bot.config import DB_PATH, ADMINS
from aiogram import Bot
from bot.config import ADMINS
import time
from bot.config import API_TOKEN
import logging

logging.basicConfig(level=logging.INFO)
logging.info(f"Импортирован tasks из {__name__}")

bot = Bot(token=API_TOKEN)
router = Router()


# ===== Функции начисления зарплаты и бонусов =====
def add_salary(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_salary INTEGER DEFAULT 0,
            total_bonus INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        INSERT INTO user_stats(user_id, total_salary) VALUES(?, ?)
        ON CONFLICT(user_id) DO UPDATE SET total_salary = total_salary + ?
    """, (user_id, amount, amount))
    conn.commit()
    conn.close()


def add_bonus(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_salary INTEGER DEFAULT 0,
            total_bonus INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        INSERT INTO user_stats(user_id, total_bonus) VALUES(?, ?)
        ON CONFLICT(user_id) DO UPDATE SET total_bonus = total_bonus + ?
    """, (user_id, amount, amount))
    conn.commit()
    conn.close()


# Просмотр задач пользователем
@router.message(F.text == "📋 Задачи")
async def show_tasks(message: types.Message):
    tasks = get_tasks()
    if not tasks:
        await message.answer(
            "😔 <b>Упс!</b>\n"
            "На данный момент доступных задач нет.\n\n"
            "📌 Попробуйте позже или свяжитесь с администратором, если это ошибка.",
            parse_mode="HTML"
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{addr_title or 'Адрес не указан'} | 👤 {executor_fio or 'Не назначен'}",
                callback_data=f"take_{tid}"
            )]
            for tid, title, desc, safe_code, comment, addr_id, addr_title, floor, apartment, executor_fio, executor_id in tasks
        ]
    )

    await message.answer(
        "🚀 Готовы к действию?\n\n"
        "Перед началом уборки обязательно ознакомьтесь с чек-листом 🧹 «Что входит в уборку», "
        "чтобы всё было идеально!\n\n"
        "Вот список задач, которые ждут вашего мастерства:\n"
        "💡 Нажмите на любую задачу ниже, чтобы взять её в работу и заработать бонусы!",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("take_"))
async def take_task(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    tasks = get_tasks()
    task = next((t for t in tasks if t[0] == task_id), None)

    if not task:
        await callback.answer("⚠️ Задача не найдена.", show_alert=True)
        return

    tid, title, desc, safe_code, comment, addr_id, addr_title, floor, apartment, executor_fio, executor_id = task

    try:
        executor_id = int(executor_id) if executor_id is not None else None
    except (ValueError, TypeError):
        executor_id = None

    if executor_id and callback.from_user.id != executor_id:
        executor_row = get_user(executor_id)
        executor_label = executor_row[1] if executor_row and executor_row[1] else f"ID {executor_id}"
        await callback.answer(
            f"⛔ Эта задача закреплена за {executor_label}.\n"
            "Вы не можете её взять. Выберите другую задачу или свяжитесь с админом, если это ошибка.",
            show_alert=True
        )
        return

    if not executor_id:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("UPDATE tasks SET executor_id = ? WHERE id = ?", (callback.from_user.id, tid))
            conn.commit()
        except Exception as e:
            logging.error("Ошибка при установке исполнителя в БД: %s", e)
        finally:
            conn.close()

    address = addr_title or "Не указан"
    floor = floor or "Не указан"
    apartment = apartment or "Не указана"

    await state.update_data(
        task_id=tid,
        address=address,
        floor=floor,
        apartment=apartment,
        description=desc or "Нет описания",
        safe_code=safe_code or "",
        comment=comment or "",
        taken_time=time.time(),
        executor=executor_fio or callback.from_user.full_name
    )

    msg = (
        "╔════════════════════════╗\n"
        "✅ <b>Задача закреплена за вами и взята в работу!</b>\n"
        "╚════════════════════════╝\n\n"
        f"🏠 <b>Адрес:</b> {address}\n"
        f"⬆️ <b>Этаж:</b> {floor}\n"
        f"🏢 <b>Квартира:</b> {apartment}\n"
        f"📝 <b>Задача:</b> {title or '-'}\n"
        f"📖 <b>Описание:</b> {desc or '-'}\n"
    )
    if safe_code:
        msg += f"🔐 <b>Код от сейфа:</b> {safe_code}\n"
    if comment:
        msg += f"💬 <b>Комментарий:</b> {comment}\n"

    await callback.message.answer(msg, parse_mode="HTML")

    user_row = get_user(callback.from_user.id)
    fio = user_row[1] if user_row else callback.from_user.full_name
    username = f"@{callback.from_user.username}" if callback.from_user.username else f"ID: {callback.from_user.id}"
    taken_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    for admin_id in ADMINS:
        try:
            await callback.bot.send_message(
                int(admin_id),
                (
                    "⚠️ <b>Задача взята в работу!</b>\n\n"
                    f"👤 <b>Исполнитель:</b> {fio}\n"
                    f"🆔 <b>Аккаунт:</b> {username}\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>Адрес:</b> {address}\n"
                    f"📝 <b>Задача:</b> {title}\n"
                    f"⏰ <b>Время:</b> {taken_at}\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    "⏳ <i>Ожидаем подтверждения выполнения.</i>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"❌ Не удалось отправить админу {admin_id}: {e}")

        # 🔔 Уведомление менеджерам (по должности в БД)
    try:

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE rank = 'manager'")
        manager_ids = [row[0] for row in cur.fetchall()]
        conn.close()

        for manager_id in manager_ids:
            try:
                await callback.bot.send_message(
                    int(manager_id),
                    (
                        "⚠️ <b>Задача взята в работу!</b>\n\n"
                        f"👤 <b>Исполнитель:</b> {fio}\n"
                        f"🆔 <b>Аккаунт:</b> {username}\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"📌 <b>Адрес:</b> {address}\n"
                        f"📝 <b>Задача:</b> {title}\n"
                        f"⏰ <b>Время:</b> {taken_at}\n"
                        "━━━━━━━━━━━━━━━━━━\n\n"
                        "⏳ <i>Ожидаем подтверждения выполнения.</i>"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"❌ Не удалось отправить менеджеру {manager_id}: {e}")

    except Exception as e:
        logging.error(f"⚠️ Ошибка при уведомлении менеджеров: {e}")

    await state.set_state(TaskWork.waiting_media)
    await callback.message.answer(
        "📸 <b>Пора подтвердить выполнение!</b>\n\n"
        "Отправьте <b>фото</b> и <b>видео</b>, чтобы доказать выполнение задачи\nДо 10 штук(фото\видео).",
        parse_mode="HTML"
    )
    await callback.answer()


# === Обработка альбомов (фото/видео) ===
@router.message(TaskWork.waiting_media, F.media_group_id)
@media_group_handler
async def handle_album(messages: list[types.Message], state: FSMContext):
    photos, videos = [], []
    for msg in messages:
        if msg.photo:
            photos.append(msg.photo[-1].file_id)
        elif msg.video:
            videos.append(msg.video.file_id)

    await state.update_data(photos=photos, videos=videos)
    await messages[0].answer("✏️ Теперь напишите, чего не хватает на квартире\n(текстом).")
    await state.set_state(TaskWork.waiting_missing_text)


# === хендлер для одиночного фото/видео ===
@router.message(TaskWork.waiting_media, (F.photo | F.video) & ~F.media_group_id)
async def handle_single_media(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    videos = data.get("videos", [])

    if message.photo:
        photos.append(message.photo[-1].file_id)
    elif message.video:
        videos.append(message.video.file_id)

    await state.update_data(photos=photos, videos=videos)
    await message.answer("✏️ Теперь напишите, чего не хватает на квартире\n(текстом).")
    await state.set_state(TaskWork.waiting_missing_text)


# === Шаг 1: чего не хватает на квартире ===
@router.message(TaskWork.waiting_missing_text)
async def task_missing(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте именно текст (не фото/видео).")
        return

    data = await state.get_data()

    taken_time = data.get("taken_time")
    if taken_time:
        elapsed = time.time() - taken_time
        if elapsed < 1 * 60:  # 1 минута ожидания (для тестов)
            remaining = int((1 * 60 - elapsed) // 60) + 1
            await message.answer(
                f"⏳ Подождите немного! Задача ещё «в процессе».\n"
                f"Осталось примерно <b>{remaining} мин.</b>\n\n"
                "✏️ Как только время истечёт, напишите <b>ещё раз</b> то, чего не хватает на квартире.",
                parse_mode="HTML"
            )
            return  # важно! не даём пойти дальше

    await state.update_data(missing_text=message.text.strip())

    # 🆕 новый шаг — спрашиваем про поломки
    await message.answer(
        "🔧 <b>Есть ли поломки на квартире?</b>\n\n"
        "📸 Прикрепите фото/видео поломок или напишите <b>«-»</b>, если всё в порядке.",
        parse_mode="HTML"
    )
    await state.set_state(TaskWork.waiting_damage)

# === Шаг 2: обработка поломок ===
@router.message(TaskWork.waiting_damage)
async def handle_breakages(message: types.Message, state: FSMContext):
    data = await state.get_data()

    photos = data.get("photos") or []
    videos = data.get("videos") or []
    missing_text = data.get("missing_text", "-")
    breakage_photos = data.get("breakage_photos") or []
    breakage_videos = data.get("breakage_videos") or []

    # 🧩 если пользователь отправил текст "-"
    if message.text and message.text.strip() == "-":
        pass
    else:
        # если прислали фото или видео — добавляем их
        if message.photo:
            breakage_photos.append(message.photo[-1].file_id)
        elif message.video:
            breakage_videos.append(message.video.file_id)

    # сохраняем обновлённое состояние
    await state.update_data(
        breakage_photos=breakage_photos,
        breakage_videos=breakage_videos
    )

    # 🆕 Новый шаг
    await message.answer(
        "📄 <b>Теперь пришлите фото остатков (бумажки)</b>\n\n"
        "Без данной фотографии дальше не пустит",
        parse_mode="HTML"
    )
    await state.set_state(TaskWork.waiting_remaining_photo)


# === Шаг 3: обработка фото остатков ===
@router.message(TaskWork.waiting_remaining_photo, F.photo)
async def handle_remaining_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()

    remaining_photos = data.get("remaining_photos", [])
    remaining_photos.append(message.photo[-1].file_id)

    await state.update_data(remaining_photos=remaining_photos)

    # ✅ Всё готово — теперь сохраняем задачу
    photos = data.get("photos") or []
    videos = data.get("videos") or []
    missing_text = data.get("missing_text", "-")
    breakage_photos = data.get("breakage_photos") or []
    breakage_videos = data.get("breakage_videos") or []
    task_id = data.get("task_id")
    description = data.get("description")
    address = data.get("address", "Не указан")

    rank = get_user_rank(message.from_user.id)
    salary_value = RANKS.get(rank, {}).get("salary", 0)
    bonus_value = RANKS.get(rank, {}).get("bonus", 0)

    if not photos and not videos:
        await message.answer("❌ Вы должны отправить хотя бы одно фото или видео для подтверждения уборки!")
        await state.set_state(TaskWork.waiting_media)
        return

    save_done_task(
        message.from_user.id,
        task_id,
        description,
        photos,
        videos,
        missing_text,
        address,
        breakage_photos,
        breakage_videos,
        remaining_photos
    )

    add_salary(message.from_user.id, salary_value)
    add_bonus(message.from_user.id, bonus_value)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    # уведомляем админов и менеджеров
    user_info = get_user(message.from_user.id)
    fio = user_info[1] if user_info else message.from_user.full_name
    task_address = address

    # --- уведомление админам ---
    for admin_id in ADMINS:
        try:
            await message.bot.send_message(
                int(admin_id),
                (
                    "✅ <b>Новая выполненная задача!</b>\n\n"
                    f"👤 <b>Исполнитель:</b> {fio}\n"
                    f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
                    f"📌 <b>Адрес:</b> {task_address}\n"
                    "/admin - Для просмотра"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"❌ Не удалось отправить уведомление админу {admin_id}: {e}")

    # --- уведомление менеджерам ---
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE rank = 'manager'")
        managers = [row[0] for row in cur.fetchall()]
        conn.close()

        for manager_id in managers:
            try:
                await message.bot.send_message(
                    int(manager_id),
                    (
                        "✅ <b>Новая выполненная задача!</b>\n\n"
                        f"👤 <b>Исполнитель:</b> {fio}\n"
                        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
                        f"📌 <b>Адрес:</b> {task_address}\n"
                        "/manager - Для просмотра"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"❌ Не удалось отправить уведомление менеджеру {manager_id}: {e}")
    except Exception as e:
        logging.error(f"❌ Ошибка при получении менеджеров: {e}")

    await state.clear()
    await message.answer(
        (
            "🎉 <b>Поздравляем!</b>\n\n"
            "✅ <b>Вы успешно выполнили задачу.</b>\n"
            f"💰 <b>Начислено:</b> <code>{salary_value} ₽</code>\n"
            f"🎁 <b>Бонусы:</b> <code>+{bonus_value}</code>\n\n"
            "🔥 <i>Продолжайте в том же духе!</i>"
        ),
        parse_mode="HTML",
        reply_markup=main_kb()
    )

