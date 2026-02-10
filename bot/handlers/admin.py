import ast

from aiogram import Router, types, F
import json
from bot.config import DB_PATH
from aiogram.types import InputFile
from datetime import datetime, timedelta
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from html import escape
from bot.db import get_all_addresses, get_apartment_media, migrate_apartment_photos, add_bonus_to_user, \
    get_address_by_id
from aiogram.filters import StateFilter, state
from aiogram.filters import Command
from bot.db import get_all_users, set_user_rank, RANKS, get_monthly_cleaning_stats, add_driver_task
from bot.ranks import RANKS
from bot.db import add_simple_task
from bot.db import get_all_addresses, delete_address, delete_all_addresses
from bot.keyboards import admin_kb, back_broadcast_kb, admin_nav_docs_kb
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot.keyboards import admin_kb, main_kb
from aiogram.types import InputMediaPhoto, InputMediaVideo
from datetime import datetime
from bot.states import AddressCreate, BonusStates, PenaltyFSM, DriverTaskCreate
from bot.config import ADMINS
from bot.db import delete_task, delete_all_tasks, remove_bonuses_for_all
from bot.db import add_task_with_address
from aiogram import types
import sqlite3
from aiogram.filters import Command
from bot.db import get_tasks, get_all_addresses, get_addresses_with_tasks, add_task_with_address
from bot.db import (
    get_done_tasks, get_done_task_details, get_user,
    delete_done_task, delete_all_done_tasks_db, search_users,
     get_all_users, update_salary, update_bonus, get_user, get_user_stats, get_pending_done_tasks,
    confirm_done_task_db, delete_user,get_all_users_with_salary, add_driver_task # новая функция для сохранения задачи с комментарием
)
from bot.states import SearchUser, TaskCreate, RemoveBonus, BroadcastStates, TaskWork
from aiogram import Bot
import logging

logger = logging.getLogger(__name__)

router = Router()
rows = get_pending_done_tasks()

# Главное меню админа
@router.message(Command("admin"), F.from_user.id.in_(ADMINS))
async def admin_menu(message: types.Message):
    await message.answer(
        "🔧 Добро пожаловать в админ-панель!\n\n"
        "Здесь ты можешь управлять задачами, пользователями и бонусами. 🛠\n"
        "Выбери действие из списка ниже и вперёд! ⚡",
        reply_markup=admin_kb()
    )

# ===== Добавление задачи с внутренним комментарием =====
@router.message(F.text == "➕ Добавить задачу", F.from_user.id.in_(ADMINS))
async def add_task_start(message: types.Message, state: FSMContext):
    from bot.db import get_all_addresses
    addresses = get_all_addresses()
    if not addresses:
        await message.answer("❌ Адресов пока нет. Сначала добавьте адрес.", reply_markup=admin_kb())
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"addr_{addr_id}")]
            for addr_id, title in addresses
        ]
    )
    await message.answer("Выберите адрес для задачи:", reply_markup=kb)
    await state.set_state(TaskCreate.waiting_address)


# === выбор адреса для создания задачи ===
@router.callback_query(F.data.regexp(r"^addr_\d+$"), F.from_user.id.in_(ADMINS))
async def address_selected(callback: types.CallbackQuery, state: FSMContext):
    addr_id = int(callback.data.split("_")[1])

    await state.update_data(address_id=addr_id)
    await callback.message.answer(
        "Теперь напишите <b>название задачи</b>:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(TaskCreate.waiting_title)
    await callback.answer()


# === ввод названия задачи ===
@router.message(TaskCreate.waiting_title, F.from_user.id.in_(ADMINS))
async def task_title_entered(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Теперь напишите <b>описание задачи</b>:", parse_mode="HTML")
    await state.set_state(TaskCreate.waiting_description)


# === ввод описания ===
@router.message(TaskCreate.waiting_description, F.from_user.id.in_(ADMINS))
async def task_description_entered(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer(
        "Введите <b>код сейфа</b> (или напишите '-' если не нужен):",
        parse_mode="HTML"
    )
    await state.set_state(TaskCreate.waiting_safe_code)


# === ввод кода сейфа ===
@router.message(TaskCreate.waiting_safe_code, F.from_user.id.in_(ADMINS))
async def task_safe_code_entered(message: types.Message, state: FSMContext):
    safe_code = message.text.strip()
    if safe_code == "-":
        safe_code = ""
    elif len(safe_code) > 50:
        await message.answer("❌ Код слишком длинный, попробуйте ввести короче:")
        return

    await state.update_data(safe_code=safe_code)
    await message.answer(
        "Введите <b>комментарий</b> к задаче (или '-' если не нужен):",
        parse_mode="HTML"
    )
    await state.set_state(TaskCreate.waiting_comment)


# === ввод комментария ===
@router.message(TaskCreate.waiting_comment, F.from_user.id.in_(ADMINS))
async def task_comment_entered(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    await state.update_data(comment=comment)

    from bot.db import get_all_users  # [(id, fio, username), ...]
    users = get_all_users()
    if not users:
        await message.answer("❌ Нет доступных исполнителей. Сначала зарегистрируйте пользователей.")
        await state.clear()
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=fio if fio else (f"@{username}" if username else str(uid)),
                    callback_data=f"exec_{uid}"
                )
            ]
            for uid, fio, username in users
        ]
    )

    await message.answer("👤 Выберите исполнителя для задачи:", reply_markup=kb)
    await state.set_state(TaskCreate.waiting_executor)


@router.callback_query(F.data.startswith("exec_"))
async def task_executor_chosen(callback: types.CallbackQuery, state: FSMContext):
    logger.debug(f"[DEBUG] Callback: {callback.data}, FSM: {await state.get_state()}")

    executor_id = int(callback.data.split("_")[1])
    await state.update_data(executor_id=executor_id)

    data = await state.get_data()
    address_id = data.get("address_id")
    title = data.get("title")
    description = data.get("description")
    safe_code = data.get("safe_code")
    comment = data.get("comment")

    from bot.db import add_task_with_address, get_address_by_id, get_user
    task_id = add_task_with_address(address_id, title, description, comment, safe_code, executor_id)

    # 🏠 Берём адрес
    addr = get_address_by_id(address_id)  # (id, title, floor, apartment, description)

    if addr:
        addr_title = addr[1]  # title
        try:
            await callback.bot.send_message(
                executor_id,
                (
                    "🚀 <b>Вам назначена новая задача!</b>\n\n"
                    f"🏠 <b>Адрес:</b> {addr_title}\n\n"
                    "📋 Зайдите в раздел «Задачи», чтобы приступить к работе."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление исполнителю {executor_id}: {e}")

    await state.clear()
    await callback.message.answer(
        "✅ Задача добавлена с назначенным исполнителем!",
        reply_markup=admin_kb()
    )
    await callback.answer()



@router.message(F.text == "➕ Добавить адрес", F.from_user.id.in_(ADMINS))
async def add_address_start(message: types.Message, state: FSMContext):
    await message.answer("Введите название адреса:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AddressCreate.waiting_title)


@router.message(AddressCreate.waiting_title, F.from_user.id.in_(ADMINS))
async def add_address_floor(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Введите этаж:")
    await state.set_state(AddressCreate.waiting_floor)


@router.message(AddressCreate.waiting_floor, F.from_user.id.in_(ADMINS))
async def add_address_apartment(message: types.Message, state: FSMContext):
    await state.update_data(floor=message.text.strip())
    await message.answer("Введите номер квартиры:")
    await state.set_state(AddressCreate.waiting_apartment)


@router.message(AddressCreate.waiting_apartment, F.from_user.id.in_(ADMINS))
async def add_address_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title")
    floor = data.get("floor")
    apartment = message.text.strip()

    from bot.db import add_address, get_all_addresses
    add_address(title, floor, apartment)
    await state.clear()

    # После добавления адреса — обновляем список адресов
    addresses = get_all_addresses()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{a[1]} — этаж {a[2]}, кв. {a[3]}", callback_data=f"addr_{a[0]}")]
        for a in addresses
    ])
    await message.answer(
        f"✅ Адрес <b>{title}</b> (этаж {floor}, кв. {apartment}) успешно добавлен!\n\n📍 Список всех адресов:",
        parse_mode="HTML",
        reply_markup=kb
    )

# ===== Утилита для безопасного парсинга JSON =====
def parse_json_field(field):
    if not field:
        return []
    try:
        return json.loads(field)
    except Exception:
        try:
            return ast.literal_eval(field)
        except Exception:
            return []


# ===== 1️⃣ Показываем список адресов =====
@router.message(F.text == "✅ Выполненные задачи", F.from_user.id.in_(ADMINS))
async def show_completed_tasks(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.address, a.title, a.floor, a.apartment, d.completed_at, d.fio
        FROM done_tasks d
        LEFT JOIN addresses a ON d.addr_id = a.id
        ORDER BY a.title, d.completed_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("✅ Нет выполненных задач.")
        return

    addresses = {}
    for done_id, addr_text, title, floor, apartment, completed_at, fio in rows:
        addr_name = f"{title}, этаж {floor}, кв. {apartment}" if title else (addr_text or "❓ Неизвестный адрес")
        addresses.setdefault(addr_name, []).append((done_id, fio, completed_at))

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏠 {addr}", callback_data=f"addr_done_{i}")]
            for i, addr in enumerate(addresses.keys())
        ]
    )

    # ✅ сохраняем карту адресов в FSM
    await state.update_data(done_tasks_map=addresses)

    await message.answer("📁 Выберите адрес:", reply_markup=kb)


# ===== 2️⃣ Показ задач по выбранному адресу =====
@router.callback_query(F.data.startswith("addr_done_"), F.from_user.id.in_(ADMINS))
async def show_tasks_in_address(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    addresses = data.get("done_tasks_map", {})

    index = int(callback.data.split("_")[-1])
    address_name = list(addresses.keys())[index]
    tasks = addresses[address_name]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{datetime.fromisoformat(completed_at).strftime('%d.%m %H:%M')} ({fio})",
                    callback_data=f"done_{done_id}"
                )
            ]
            for done_id, fio, completed_at in tasks
        ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_done_list")]]
    )

    await callback.message.edit_text(
        f"📋 <b>{address_name}</b>\nВыберите выполненную задачу:",
        parse_mode="HTML",
        reply_markup=kb
    )


# ===== 3️⃣ Возврат к списку адресов =====
@router.callback_query(F.data == "back_to_done_list", F.from_user.id.in_(ADMINS))
async def back_to_address_list(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    addresses = data.get("done_tasks_map", {})

    if not addresses:
        await callback.message.edit_text("❌ Данные не найдены. Попробуйте снова нажать '✅ Выполненные задачи'.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏠 {addr}", callback_data=f"addr_done_{i}")]
            for i, addr in enumerate(addresses.keys())
        ]
    )

    await callback.message.edit_text("📁 Выберите адрес:", reply_markup=kb)


# ===== 4️⃣ Просмотр деталей выполненной задачи =====
@router.callback_query(F.data.startswith("done_"), F.from_user.id.in_(ADMINS))
async def show_done_task_details(callback: types.CallbackQuery, state: FSMContext):
    import json
    from aiogram.types import InputMediaPhoto, InputMediaVideo

    def parse_json_field(field):
        """Безопасное извлечение списка file_id из JSON."""
        if not field:
            return []
        if isinstance(field, list):
            return field
        try:
            data = json.loads(field)
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    done_task_id = int(callback.data.split("_")[1])
    done_task = get_done_task_details(done_task_id)
    if not done_task:
        await callback.message.edit_text("❌ Задача не найдена")
        return

    user_id, addr_id, fio, photos_json, videos_json, missing_text, completed_at, description, breakage_photos, breakage_videos = done_task

    # === Определяем адрес ===
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT title, floor, apartment FROM addresses WHERE id = ?", (addr_id,))
    addr_row = cur.fetchone()
    if addr_row:
        address = f"{addr_row[0]}, этаж {addr_row[1]}, кв. {addr_row[2]}"
    else:
        cur.execute("SELECT address FROM done_tasks WHERE id = ?", (done_task_id,))
        addr_txt = cur.fetchone()
        address = addr_txt[0] if addr_txt and addr_txt[0] else "❓ Неизвестный адрес"
    conn.close()

    # === Текст задачи ===
    text = (
        f"✅ <b>Выполненная задача</b>\n\n"
        f"🏠 <b>Адрес:</b> {address}\n"
        f"👤 <b>Исполнитель:</b> {fio}\n"
        f"📝 <b>Описание:</b> {description or '—'}\n"
        f"⏰ <b>Выполнена:</b> {datetime.fromisoformat(completed_at).strftime('%d.%m.%Y %H:%M')}"
    )
    if missing_text:
        text += f"\n💬 <b>Чего не хватает:</b> {missing_text}"

    # === Фото / Видео ===
    photos = parse_json_field(photos_json)
    videos = parse_json_field(videos_json)

    media_list = []
    for p in photos:
        media_list.append(InputMediaPhoto(media=p))
    for v in videos:
        media_list.append(InputMediaVideo(media=v))

    # Ограничение Telegram — максимум 10 медиа в одной группе
    if media_list:
        try:
            for i in range(0, len(media_list), 10):
                await callback.message.answer_media_group(media_list[i:i + 10])
        except Exception as e:
            await callback.message.answer(f"⚠️ Ошибка при отправке медиа: {e}")
    else:
        await callback.message.answer("📭 Фото и видео не найдены для этой задачи.")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Поломки", callback_data=f"breakages_{done_task_id}")],
            [InlineKeyboardButton(text="📄 Остатки", callback_data=f"remaining_{done_task_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_done_list")]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)



# ====== Поломки ======
@router.callback_query(F.data.startswith("breakages_"), F.from_user.id.in_(ADMINS))
async def show_breakages(callback: types.CallbackQuery):
    done_task_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT breakage_photos, breakage_videos FROM done_tasks WHERE id = ?", (done_task_id,))
    row = cur.fetchone()
    conn.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"done_{done_task_id}")]])

    if not row:
        await callback.message.edit_text("❌ Нет данных о поломках.", reply_markup=kb)
        return

    def safe_parse(data):
        if isinstance(data, list): return data
        try: return json.loads(data or "[]")
        except: return []

    photos = safe_parse(row[0])
    videos = safe_parse(row[1])

    if not photos and not videos:
        await callback.message.edit_text("✅ Поломок не обнаружено.", reply_markup=kb)
        return

    await callback.message.edit_text("🔧 Фото/видео поломок:", reply_markup=kb)
    await callback.message.answer_media_group([InputMediaPhoto(media=p) for p in photos] + [InputMediaVideo(media=v) for v in videos])


# ====== Остатки ======
@router.callback_query(F.data.startswith("remaining_"), F.from_user.id.in_(ADMINS))
async def show_remaining_photos(callback: types.CallbackQuery):
    done_task_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT remaining_photos FROM done_tasks WHERE id = ?", (done_task_id,))
    row = cur.fetchone()
    conn.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"done_{done_task_id}")]])

    if not row:
        await callback.message.edit_text("❌ Нет данных об остатках.", reply_markup=kb)
        return

    def safe_parse(data):
        if isinstance(data, list): return data
        try: return json.loads(data or "[]")
        except: return []

    photos = safe_parse(row[0])

    if not photos:
        await callback.message.edit_text("📭 Остатков не найдено.", reply_markup=kb)
        return

    await callback.message.edit_text("📄 Фото остатков (бумажки):", reply_markup=kb)
    await callback.message.answer_media_group([InputMediaPhoto(media=p) for p in photos])




# ===== Удаление выполненных задач =====
PAGE_SIZE = 10  # количество задач на одной странице

@router.message(F.text == "🗑 Очистить выполненные", F.from_user.id.in_(ADMINS))
async def delete_done_tasks_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Удалить все", callback_data="confirm_delete_all_done")],
        [InlineKeyboardButton(text="📝 Выбрать конкретные", callback_data="delete_select_done_0")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_cancel")]
    ])
    await message.answer("Выберите действие с выполненными задачами:", reply_markup=kb)


@router.callback_query(F.data == "confirm_delete_all_done", F.from_user.id.in_(ADMINS))
async def confirm_delete_all(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить все", callback_data="delete_all_done")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_cancel")]
    ])
    await callback.message.edit_text("Вы уверены, что хотите удалить все выполненные задачи?", reply_markup=kb)


@router.callback_query(F.data == "delete_all_done", F.from_user.id.in_(ADMINS))
async def delete_all_done(callback: types.CallbackQuery):
    delete_all_done_tasks_db()
    await callback.message.edit_text("✅ Все выполненные задачи удалены.")


# === выбор конкретных задач (с пагинацией) ===
@router.callback_query(F.data.regexp(r"^delete_select_done_(\d+)$"), F.from_user.id.in_(ADMINS))
async def select_done_tasks(callback: types.CallbackQuery):
    PAGE_SIZE = 10  # кол-во задач на странице
    page = int(callback.data.split("_")[-1])
    rows = get_done_tasks()  # должен возвращать (done_id, address, fio, completed_at)
    if not rows:
        await callback.message.edit_text("Нет выполненных задач для удаления.")
        return

    total_pages = (len(rows) - 1) // PAGE_SIZE + 1
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_rows = rows[start:end]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{address or 'Без адреса'} | {completed_at or '—'} | {fio}",
                callback_data=f"delete_done_{done_id}"
            )]
            for done_id, address, fio, completed_at in page_rows
        ]
    )

    # Навигация между страницами
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"delete_select_done_{page-1}"))
    if end < len(rows):
        nav_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"delete_select_done_{page+1}"))
    if nav_buttons:
        kb.inline_keyboard.append(nav_buttons)

    # Кнопка отмены
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="delete_cancel")])

    await callback.message.edit_text(
        f"Выберите задачи для удаления (страница {page+1}/{total_pages}):",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("delete_done_"), F.from_user.id.in_(ADMINS))
async def delete_specific_done(callback: types.CallbackQuery):
    done_id = int(callback.data.split("_")[2])
    delete_done_task(done_id)
    await callback.answer("Задача удалена ✅", show_alert=False)

    rows = get_done_tasks()
    if not rows:
        await callback.message.edit_text("Все задачи удалены ✅")
        return

    await select_done_tasks(callback)


@router.callback_query(F.data == "delete_cancel", F.from_user.id.in_(ADMINS))
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Действие отменено.")


# ===== Поиск пользователя =====
@router.message(F.text == "🔍 Найти пользователя", F.from_user.id.in_(ADMINS))
async def start_search(message: types.Message, state: FSMContext):
    await message.answer(
        "🔎 <b>Поиск пользователя</b>\n\n"
        "Введите <i>ФИО</i> или <i>номер телефона</i> для поиска:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(SearchUser.waiting_query)


@router.message(SearchUser.waiting_query, F.from_user.id.in_(ADMINS))
async def process_search(message: types.Message, state: FSMContext):
    query = message.text.strip()
    results = search_users(query)  # вернёт [(user_id, fio, phone, district, reg_at), ...] — лучше допиши reg_at в функцию
    await state.clear()

    if not results:
        await message.answer("❌ <b>Пользователь не найден.</b>", parse_mode="HTML", reply_markup=admin_kb())
        return

    for user_id, fio, phone, district, reg_at in results:
        # получаем зарплату/бонусы по user_id
        total_salary, total_bonus = get_user_stats(user_id)

        text = (
            f"👤 <b>Профиль пользователя</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"📛 <b>ФИО:</b> {fio}\n"
            f"📱 <b>Телефон:</b> {phone}\n"
            f"📍 <b>Район:</b> {district}\n"
            f"💰 <b>Зарплата:</b> {total_salary} ₽\n"
            f"🎁 <b>Бонусы:</b> {total_bonus}\n"
            f"🗓 <b>Зарегистрирован:</b> {reg_at}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

        await message.answer(text, parse_mode="HTML", reply_markup=admin_kb())

# Обнуление ЗП всех пользователей
@router.message(lambda message: message.text == "💰 Обнулить ЗП" and message.from_user.id in ADMINS)
async def reset_salary(message: types.Message, bot: Bot):
    # 1. Обнуляем ЗП всем пользователям
    update_salary(set_absolute=True, value=0)

    # 2. Формируем дату/время в читаемом формате
    now = datetime.now()
    formatted_date = now.strftime("%d.%m.%Y %H:%M")

    # 3. Получаем всех пользователей
    users = get_all_users()  # [(id, fio, phone, district, salary, bonus, ...)]

    notified = 0
    for user in users:
        user_id = user[0]
        fio = user[1] if len(user) > 1 else "Пользователь"

        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "💸 <b>Выплата произведена!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💰 <b>Сумма успешно зачислена на ваш счёт.</b>\n"
                    f"📅 <b>Дата операции:</b> <i>{formatted_date}</i>\n\n"
                    "⚡ <b>Спасибо за вашу работу и вклад!</b>\n"
                    "💬 <i>Есть вопросы? Свяжитесь с администратором.</i>\n"
                    "━━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode="HTML"
            )
            notified += 1
        except Exception as e:
            import logging
            logging.warning(f"Ошибка отправки уведомления {user_id}: {e}")

    # 4. Подтверждение для админа
    await message.answer(
        f"💰 ЗП всех пользователей (включая админов) обнулена!\n"
        f"📬 Уведомлено пользователей: {notified}"
    )


# Начало удаления бонусов
@router.message(F.text == "📉 Удалить бонусы", F.from_user.id.in_(ADMINS))
async def start_remove_bonus(message: types.Message, state: FSMContext):
    # Главное меню для удаления бонусов
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить бонусы всем", callback_data="remove_all")],
            [InlineKeyboardButton(text="👤 Удалить конкретному", callback_data="remove_choose_user")]
        ]
    )
    await message.answer("Выберите способ удаления бонусов:", reply_markup=kb)
    await state.clear()

# Обработчик "удалить всем"
@router.callback_query(F.data == "remove_all")
async def remove_all_bonuses(callback: types.CallbackQuery):
    # тут вызываешь функцию для сброса бонусов у всех
    remove_bonuses_for_all()  # ты должен реализовать эту функцию в utils/db
    await callback.message.answer("✅ Все бонусы успешно обнулены.")
    await callback.answer()


# Обработчик "удалить конкретному"
@router.callback_query(F.data == "remove_choose_user")
async def remove_choose_user(callback: types.CallbackQuery, state: FSMContext):
    users = get_all_users()  # [(id, fio, ...), ...]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=fio, callback_data=f"remove_{uid}")]
                         for uid, fio, *rest in users]  # игнорируем лишние элементы
    )
    await callback.message.answer("👤 Выберите пользователя, у которого нужно удалить бонусы:", reply_markup=kb)
    await state.set_state(RemoveBonus.waiting_user)
    await callback.answer()

# Выбор пользователя
@router.callback_query(F.data.startswith("remove_"), F.from_user.id.in_(ADMINS))
async def choose_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    await state.update_data(user_id=user_id)
    await callback.message.answer("Введите количество бонусов, которые нужно удалить:")
    await state.set_state(RemoveBonus.waiting_amount)

# Ввод количества бонусов
@router.message(RemoveBonus.waiting_amount, F.from_user.id.in_(ADMINS))
async def input_bonus_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректное число бонусов (>0).")
        return
    await state.update_data(amount=amount)
    await message.answer("Введите причину снятия бонусов:")
    await state.set_state(RemoveBonus.waiting_reason)

# Ввод причины и завершение
@router.message(RemoveBonus.waiting_reason, F.from_user.id.in_(ADMINS))
async def input_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    amount = data.get("amount")
    reason = message.text.strip()

    if not user_id or not amount:
        await message.answer("❌ Ошибка состояния. Попробуйте снова.")
        await state.clear()
        return

    # ===== Логи =====
    print(f"[DEBUG] FSM data: {data}")
    print(f"[DEBUG] user_id: {user_id}, amount: {amount}, reason: {reason}")

    # Получаем текущий бонус пользователя из user_stats
    total_salary, current_bonus = get_user_stats(user_id)
    print(f"[DEBUG] current_bonus from user_stats: {current_bonus}")

    # Снимаем максимум доступного
    to_remove = min(amount, current_bonus)
    if to_remove == 0:
        await message.answer("У пользователя нет бонусов для снятия.")
        print("[DEBUG] Бонусов для снятия нет")
        await state.clear()
        return

    # Обновляем бонусы через update_bonus (работает с user_stats.total_bonus)
    update_bonus(user_id, -to_remove)

    user_info = get_user(user_id)
    fio = user_info[1] if user_info else "Пользователь"

    # Уведомление пользователю
    await message.bot.send_message(
        user_id,
        f"⚠️ У вас сняли {to_remove} бонусов.\nПричина: {reason}"
    )

    # Уведомление админу
    await message.answer(f"✅ Снято {to_remove} бонусов у {fio}.\nПричина: {reason}")
    await state.clear()


    # Очистка состояния
    await state.clear()

@router.message(lambda m: m.text == "👥 Все пользователи" and m.from_user.id in ADMINS)
async def list_all_users(message: types.Message):
    users = get_all_users()  # [(user_id, fio, username), ...]
    if not users:
        await message.answer("❌ Пользователей нет.", reply_markup=ReplyKeyboardRemove())
        return

    text_lines = []
    for user_id, fio, username in users:
        username_display = f"@{username}" if username else "—"
        fio_display = fio if fio else "❓ (не указано)"
        text_lines.append(f"🆔 {user_id}\n📛 {fio_display}\n👤 {username_display}")
        text_lines.append("──────────")

    # Разбиваем сообщение на части (чтобы не упереться в лимит 4096 символов)
    CHUNK_SIZE = 30
    for i in range(0, len(text_lines), CHUNK_SIZE):
        chunk = text_lines[i:i + CHUNK_SIZE]
        await message.answer("\n".join(chunk), parse_mode="HTML")


@router.message(lambda message: message.text == "📢 Сообщение всем" and message.from_user.id in ADMINS)
async def start_broadcast(message: types.Message, state: FSMContext):
    await message.answer(
        "✏️ <b>Введите текст рассылки</b>\n\n"
        "Это сообщение получат <b>все пользователи</b> бота.\n"
        "🔙 Если передумали — нажмите кнопку <b>«Назад»</b> ниже 👇",
        reply_markup=back_broadcast_kb(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_message)


# Обработка «Назад» (отмена рассылки)
@router.message(BroadcastStates.waiting_message, lambda m: m.text == "🔙 Назад" and m.from_user.id in ADMINS)
async def cancel_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Рассылка отменена.", reply_markup=admin_kb())  # возвращаем панель админа


# Получаем сообщение и рассылаем
@router.message(BroadcastStates.waiting_message, lambda message: message.from_user.id in ADMINS)
async def send_broadcast(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Сообщение не может быть пустым. Попробуйте снова.")
        return

    users = get_all_users()  # [(user_id, fio), ...]
    count_sent = 0

    for user_id, *_ in users:  # игнорируем лишние элементы
        try:
            await message.bot.send_message(
                user_id,
                f"📢 Сообщение от администраторов:\n\n{text}"
            )
            count_sent += 1
        except Exception as e:
            print(f"Не удалось отправить пользователю {user_id}: {e}")
            pass

    await state.clear()

    await message.answer(
        f"📤 Сообщение отправлено {count_sent} пользователям.",
        reply_markup=admin_kb()  # ← возвращаем панель админа
    )


@router.message(F.text == "❌ Удалить пользователя", F.from_user.id.in_(ADMINS))
async def start_delete_user(message: types.Message):
    users = get_all_users()  # [(user_id, fio, ...)]
    if not users:
        await message.answer("❌ Пользователей нет для удаления.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=fio or f"ID {uid}",  # если fio = None, используем fallback
                    callback_data=f"delete_{uid}"
                )
            ]
            for uid, fio, *_ in users
        ]
    )
    await message.answer("Выберите пользователя для удаления:", reply_markup=kb)

# Подтверждение удаления
@router.callback_query(lambda c: c.data.startswith("delete_") and not c.data.startswith("delete_task_"), F.from_user.id.in_(ADMINS))
async def confirm_delete_user(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    last = parts[-1]

    if last == "all":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚠️ Да, удалить всех", callback_data="confirm_delete_all")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
            ]
        )
        await callback.message.edit_text("Вы уверены, что хотите удалить всех пользователей?", reply_markup=kb)
    else:
        user_id = int(last)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚠️ Да, удалить", callback_data=f"confirm_delete_{user_id}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
            ]
        )
        await callback.message.edit_text("Вы уверены, что хотите удалить этого пользователя?", reply_markup=kb)


@router.callback_query(lambda c: c.data.startswith("confirm_delete_") and not c.data.startswith("confirm_delete_task_"), F.from_user.id.in_(ADMINS))
async def delete_user_callback(callback: types.CallbackQuery):
    last = callback.data.split("_")[-1]
    if last == "all":
        # delete_all_users() — твоя функция
        await callback.message.edit_text("✅ Все пользователи удалены.")
    else:
        user_id = int(last)
        delete_user(user_id)
        await callback.message.edit_text("✅ Пользователь удален.")

# Отмена действия
@router.callback_query(F.data == "cancel_delete", F.from_user.id.in_(ADMINS))
async def cancel_delete_user(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Действие отменено.")

@router.message(F.text == "🗑 Удалить задачи", F.from_user.id.in_(ADMINS))
async def delete_tasks_menu(message: types.Message):
    tasks = get_tasks()
    if not tasks:
        await message.answer("❌ Нет невыполненных задач.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Удалить все", callback_data="delete_all_tasks")],
            *[
                [InlineKeyboardButton(
                    text=f"{addr_title or 'Без адреса'} | {title}",
                    callback_data=f"delete_task_{tid}"
                )]
                # теперь 11 переменных
                for tid, title, desc, safe_code, comment, addr_id, addr_title, floor, apartment, executor, created_at in tasks
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete_tasks")]
        ]
    )
    await message.answer("Выберите задачу для удаления или удалите все сразу:", reply_markup=kb)



@router.callback_query(F.data.startswith("delete_task_"), F.from_user.id.in_(ADMINS))
async def delete_specific_task(callback: types.CallbackQuery):
    try:
        task_id = int(callback.data.split("_")[2])
    except ValueError:
        await callback.answer("Ошибка: неверный ID задачи", show_alert=True)
        return

    delete_task(task_id)
    await callback.answer("Задача удалена ✅", show_alert=False)

    # Обновляем список задач
    tasks = get_tasks()
    if not tasks:
        await callback.message.edit_text("Все задачи удалены ✅")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{addr_title or 'Без адреса'} | {title}",
                callback_data=f"delete_task_{tid}"
            )]
            for tid, title, desc, safe_code, comment, addr_id, addr_title, floor, apartment, executor, created_at in tasks
        ]
    )
    kb.inline_keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete_tasks")])
    await callback.message.edit_text("Выберите задачу для удаления:", reply_markup=kb)



@router.callback_query(F.data == "delete_all_tasks", F.from_user.id.in_(ADMINS))
async def delete_all_tasks_cb(callback: types.CallbackQuery):
    delete_all_tasks()
    await callback.message.edit_text("✅ Все невыполненные задачи удалены.")


@router.callback_query(F.data == "cancel_delete_tasks", F.from_user.id.in_(ADMINS))
async def cancel_delete_tasks(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Действие отменено.")

@router.message(F.text == "📊 Посмотреть ЗП всех", F.from_user.id.in_(ADMINS))
async def show_all_salaries(message: types.Message):
    users = get_all_users_with_salary()
    if not users:
        await message.answer("❌ Список пользователей пуст.")
        return

    text_lines = ["📊 <b>Текущая зарплата всех сотрудников:</b>\n"]

    for _, fio, total_salary, total_bonus, total_penalty in users:
        final_salary = total_salary + total_bonus - total_penalty

        text_lines.append(
            f"👤 <b>{fio or 'Без ФИО'}</b>\n"
            f"💵 Зарплата: <b>{total_salary} ₽</b>\n"
            f"🎁 Бонусы: <b>{total_bonus} ₽</b>\n"
            f"🚫 Штрафы: <b>-{total_penalty} ₽</b>\n"
            f"📊 Итого: <b>{final_salary} ₽</b>\n"
            "────────────────────────"
        )
    await message.answer("\n".join(text_lines), parse_mode="HTML")


@router.message(F.text == "ℹ️ Навигация админ-панели")
async def admin_help(message: types.Message):
    text = (
        "⚙️ <b>Навигация по админ-панели</b>\n\n"
        "Добро пожаловать в панель управления! Здесь собраны все инструменты администратора 👇\n\n"

        "📌 <b>Управление задачами</b>\n"
        "• ➕ <b>Добавить задачу</b> – создать новую задачу для адреса.\n"
        "• ✅ <b>Выполненные задачи</b> – список завершённых.\n"
        "• 🗑 <b>Очистить выполненные</b> – удалить весь список выполненных.\n"
        "• 🗑 <b>Удалить задачи</b> – удалить активные задачи (выборочно или все).\n\n"

        "🏠 <b>Работа с адресами</b>\n"
        "• ➕ <b>Добавить адрес</b> – внести новый адрес (с этажом и квартирой).\n"
        "• 🗑 <b>Удалить адрес</b> – удалить один или все адреса.\n\n"

        "👤 <b>Пользователи</b>\n"
        "• 🔍 <b>Найти пользователя</b> – поиск по ФИО или телефону.\n"
        "• ❌ <b>Удалить пользователя</b> – полное удаление из базы.\n"
        "• 👥 <b>Все пользователи</b> – список зарегистрированных.\n\n"

        "💰 <b>Финансы</b>\n"
        "• 📉 <b>Удалить бонусы</b> – обнулить бонусы.\n"
        "• 💰 <b>Обнулить ЗП</b> – сбросить зарплаты.\n"
        "• 📊 <b>Посмотреть ЗП всех</b> – таблица зарплат и бонусов.\n\n"

        "📢 <b>Коммуникация</b>\n"
        "• 📢 <b>Сообщение всем</b> – массовая рассылка пользователям.\n\n"

        "↩️ <b>Прочее</b>\n"
        "• ⬅️ <b>Назад в меню</b> – возврат в обычное меню.\n\n"

        "✨ Используйте кнопки для быстрого доступа к нужной функции!"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=admin_nav_docs_kb()
    )


@router.callback_query(F.data == "doc_add_address")
async def doc_add_address(callback: types.CallbackQuery):
    text = (
        "🏠 <b>Как работать с адресами:</b>\n\n"
        "➕ <b>Добавить адрес</b>\n"
        "1️⃣ Нажми кнопку «Добавить адрес».\n"
        "2️⃣ Введи название (улица, дом).\n"
        "3️⃣ Укажи этаж и квартиру (если нужно).\n"
        "4️⃣ Подтверди.\n"
        "✅ Адрес сохранён и теперь доступен при создании задач.\n\n"

        "🗑 <b>Удалить адрес</b>\n"
        "1️⃣ Нажми кнопку «Удалить адрес».\n"
        "2️⃣ Выбери конкретный адрес для удаления или удали все сразу.\n"
        "⚠️ Внимание: вместе с адресом можно удалить и привязанные задачи (если включить каскадное удаление)."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_nav_docs_kb())
    await callback.answer()



@router.callback_query(F.data == "doc_add_task")
async def doc_add_task(callback: types.CallbackQuery):
    text = (
        "📌 <b>Как добавить задачу:</b>\n\n"
        "1️⃣ Нажми кнопку <b>«➕ Добавить задачу»</b>.\n"
        "2️⃣ Введи описание задачи (что нужно сделать).\n"
        "3️⃣ Выбери адрес из списка или добавь новый.\n"
        "4️⃣ Укажи этаж, квартиру, комментарий и код от сейфа (если нужно).\n"
        "5️⃣ Подтверди добавление.\n\n"
        "✅ Теперь задача появится у пользователей."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_nav_docs_kb())
    await callback.answer()


@router.callback_query(F.data == "doc_add_address")
async def doc_add_address(callback: types.CallbackQuery):
    text = (
        "🏠 <b>Как добавить адрес:</b>\n\n"
        "1️⃣ Нажми кнопку <b>«➕ Добавить адрес»</b>.\n"
        "2️⃣ Введи название (улица, дом).\n"
        "3️⃣ Укажи этаж и квартиру (если нужно).\n"
        "4️⃣ Подтверди.\n\n"
        "✅ Адрес сохранён и теперь доступен при создании задач."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_nav_docs_kb())
    await callback.answer()


@router.callback_query(F.data == "doc_users")
async def doc_users(callback: types.CallbackQuery):
    text = (
        "👤 <b>Работа с пользователями:</b>\n\n"
        "• <b>🔍 Найти пользователя</b> – вводишь имя или телефон, бот найдёт.\n"
        "• <b>❌ Удалить пользователя</b> – полностью убирает из базы.\n"
        "• <b>👥 Все пользователи</b> – выдаёт список всех зарегистрированных.\n\n"
        "⚠️ Будь осторожен с удалением — восстановить пользователя потом нельзя!"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_nav_docs_kb())
    await callback.answer()


@router.callback_query(F.data == "doc_finance")
async def doc_finance(callback: types.CallbackQuery):
    text = (
        "💰 <b>Работа с финансами:</b>\n\n"
        "• <b>📉 Удалить бонусы</b> – можно обнулить бонусы всем или конкретному юзеру.\n"
        "• <b>💰 Обнулить ЗП</b> – сброс зарплат сразу у всех.\n"
        "• <b>📊 Посмотреть ЗП всех</b> – таблица с зарплатами и бонусами.\n\n"
        "💡 Полезно для контроля выплат и статистики."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_nav_docs_kb())
    await callback.answer()

@router.callback_query(F.data == "doc_back")
async def doc_back(callback: types.CallbackQuery):
    await admin_help(callback.message)  # просто возвращаемся к исходному тексту
    await callback.answer()


@router.message(F.text == "📖 Admin F.A.Q.")
async def admin_faq(message: types.Message):
    text = (
        "🔒 <b>Admin F.A.Q. и Политика использования</b>\n\n"
        "👋 Добро пожаловать в админ-панель!\n"
        "Перед тем как начать работать, важно помнить несколько простых, но серьёзных правил. "
        "Они помогают сохранить порядок, защитить данные и избежать проблем.\n\n"

        "📌 <b>1. Доступ к админке</b>\n"
        "🔑 Админ-доступ — это ваш персональный ключ. Никому его не передавайте.\n"
        "❌ Пароли, коды, токены и любые данные для входа запрещено делиться с третьими лицами.\n\n"

        "📌 <b>2. Ответственность</b>\n"
        "📝 Все действия через ваш аккаунт считаются вашими личными.\n"
        "⚖️ Разработчик отвечает только за техническую стабильность, "
        "но не за решения, которые принимаются администратором.\n"
        "👤 Ответственность за рассылки, обнуление зарплат, удаление задач и другие операции "
        "лежит исключительно на администраторе.\n\n"

        "📌 <b>3. Что категорически запрещено</b>\n"
        "🚫 Злоупотреблять функциями (спам, тестирование по 100 раз подряд и т.д.).\n"
        "🚫 Удалять данные или менять показатели без причины.\n"
        "🚫 Использовать бота в личных целях.\n"
        "🚫 Делать массовые действия без понимания последствий.\n\n"

        "📌 <b>4. Конфиденциальность</b>\n"
        "🔒 Вся информация внутри админки — строго внутренняя.\n"
        "📸 Запрещено делать скриншоты и пересылать данные посторонним.\n"
        "🕵️ Контакты и доступы к боту нельзя передавать третьим лицам.\n\n"

        "📌 <b>5. Поддержка и роль разработчика</b>\n"
        "👨‍💻 Разработчик обеспечивает техническую работу и обновления.\n"
        "📌 Управление компанией и решения остаются за администраторами.\n"
        "⚡ Ошибки или баги сообщайте разработчику, но последствия неверных действий остаются на вас.\n\n"

        "📌 <b>6. Если правила нарушаются</b>\n"
        "❗ Возможные меры:\n"
        "• временное ограничение доступа;\n"
        "• передача информации руководству;\n"
        "• при серьёзных нарушениях — ответственность по договорённостям компании.\n\n"

        "✅ Помните: админка — это инструмент управления, а не игрушка. "
        "Используйте её с умом, и всё будет работать идеально! 🚀"
    )
    await message.answer(text, parse_mode="HTML")

# === Удаление адресов ===

@router.message(F.text == "🗑 Удалить адрес", F.from_user.id.in_(ADMINS))
async def delete_address_menu(message: types.Message):
    addresses = get_all_addresses()
    if not addresses:
        await message.answer("📭 В базе пока нет сохранённых адресов.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Удалить все", callback_data="addr_del_all")],
            *[
                [InlineKeyboardButton(
                    text=f"{addr_id} | {title}",
                    callback_data=f"addr_del_{addr_id}"
                )]
                for addr_id, title in addresses
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="addr_del_cancel")]
        ]
    )

    await message.answer("🏠 Выберите адрес для удаления:", reply_markup=kb)


@router.callback_query(F.data.startswith("addr_del_"), F.from_user.id.in_(ADMINS))
async def delete_address_callback(callback: types.CallbackQuery):
    last = callback.data[len("addr_del_"):]  # отрезаем префикс, остаётся либо число, либо "all", либо "cancel"

    if last == "cancel":
        await callback.message.edit_text("❌ Действие отменено.")
        return

    if last == "all":
        delete_all_addresses()
        await callback.message.edit_text("✅ Все адреса удалены.")
        return

    if last.isdigit():
        addr_id = int(last)
        delete_address(addr_id)
        await callback.answer("🗑 Адрес удалён!", show_alert=False)

        addresses = get_all_addresses()
        if not addresses:
            await callback.message.edit_text("✨ Все адреса удалены.")
            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Удалить все", callback_data="addr_del_all")],
                *[
                    [InlineKeyboardButton(
                        text=f"{addr_id} | {title}",
                        callback_data=f"addr_del_{addr_id}"
                    )]
                    for addr_id, title in addresses
                ],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="addr_del_cancel")]
            ]
        )
        await callback.message.edit_text("🏠 Выберите адрес для удаления:", reply_markup=kb)
        return

    await callback.answer("⚠️ Неверный ID!", show_alert=True)


@router.message(F.text == "👑 Назначить должность", F.from_user.id.in_(ADMINS))
async def choose_user_for_rank(message: types.Message):
    users = get_all_users()
    if not users:
        await message.answer("❌ Пользователей нет.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{fio} ({uid})",
                callback_data=f"setrank_{uid}"
            )]
            for uid, fio, *_ in users
        ]
    )

    await message.answer("👥 Выбери пользователя:", reply_markup=kb)


# ===== Выбор пользователя для назначения ранга =====
@router.callback_query(F.data.startswith("setrank_"), F.from_user.id.in_(ADMINS))
async def choose_rank(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=rank_data["title"], callback_data=f"rank_{uid}_{rank_key}")]
            for rank_key, rank_data in RANKS.items()
        ]
    )

    await callback.message.answer(f"👑 Выберите должность для пользователя {uid}:", reply_markup=kb)
    await callback.answer()


# ===== Подтверждение и установка ранга =====
@router.callback_query(F.data.startswith("rank_"), F.from_user.id.in_(ADMINS))
async def set_rank(callback: types.CallbackQuery):
    # Разбиваем строку callback.data только на 3 части максимум
    _, uid, rank_key = callback.data.split("_", 2)
    uid = int(uid)

    if rank_key not in RANKS:
        await callback.answer("❌ Неверная должность", show_alert=True)
        return

    set_user_rank(uid, rank_key)
    user = get_user(uid)
    fio = user[1] if user else "Пользователь"
    rank_title = RANKS[rank_key]["title"]

    await callback.message.edit_text(
        f"✅ {fio} назначен на должность: <b>{rank_title}</b>",
        parse_mode="HTML"
    )
    await callback.answer()



@router.message(lambda message: message.text == "📅 Все уборки")
async def all_cleanings_this_month(message: types.Message):
    stats = get_monthly_cleaning_stats()
    if not stats:
        await message.answer("❌ В этом месяце ещё не выполнено ни одной уборки.")
        return

    text = "📊 Уборки за текущий месяц:\n\n"
    for fio, count in stats:
        text += f"• {fio} — {count} уборок\n"

    await message.answer(text)

@router.message(F.text == "➕ Добавить бонус")
async def ask_user_fio(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите ФИО пользователя, которому хотите начислить бонус:"
    )
    await state.set_state(BonusStates.waiting_fio)


# Обработка введенного ФИО
@router.message(BonusStates.waiting_fio)
async def process_fio(message: types.Message, state: FSMContext):
    fio = message.text.strip()
    users = search_users(fio)  # функция поиска по базе, вернёт [(id, fio, phone, ...), ...]

    if not users:
        await message.answer("❌ Пользователь не найден. Попробуйте снова.")
        return

    if len(users) > 1:
        # несколько совпадений — выводим список
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=u[1], callback_data=f"bonus_user_{u[0]}")]
                for u in users
            ]
        )
        await message.answer("Найдено несколько пользователей. Выберите нужного:", reply_markup=kb)
        return

    # если один найден
    user_id = users[0][0]
    await state.update_data(user_id=user_id)
    await message.answer(f"✅ Пользователь найден: {users[0][1]}\nВведите сумму бонуса:")
    await state.set_state(BonusStates.waiting_amount)


# Обработка выбора пользователя из InlineKeyboard
@router.callback_query(F.data.startswith("bonus_user_"))
async def bonus_user_chosen(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    await state.update_data(user_id=user_id)
    await callback.message.answer("Введите сумму бонуса:")
    await state.set_state(BonusStates.waiting_amount)
    await callback.answer()


# Ввод суммы бонуса
@router.message(BonusStates.waiting_amount)
async def process_bonus_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("❌ Ошибка: пользователь не выбран. Начните сначала.")
        await state.clear()
        return

    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректное число бонусов (>0)")
        return

    # Начисляем бонус
    add_bonus_to_user(user_id, amount)

    # Уведомляем администратора
    await message.answer(f"✅ Бонус +{amount} начислен пользователю ID {user_id}")

    # Уведомляем пользователя
    try:
        user = get_user(user_id)
        fio = user[1] if user else "Пользователь"
        await message.bot.send_message(
            chat_id=user_id,
            text=f"💰 Привет, {fio}! Вам начислен бонус: +{amount}."
        )
    except Exception as e:
        import logging
        logging.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

    await state.clear()

@router.message(lambda m: m.text == "🚫 Штраф" and m.from_user.id in ADMINS)
async def start_penalty(message: types.Message, state: FSMContext):
    users = get_all_users()  # [(id, fio, ...)]
    if not users:
        await message.answer("❌ Нет зарегистрированных пользователей.")
        return

    # создаем список пользователей с inline-кнопками
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{u[1]} ({u[0]})", callback_data=f"penalty_user_{u[0]}")]
            for u in users
        ]
    )
    await message.answer("👥 Кого оштрафовать?", reply_markup=kb)
    await state.set_state(PenaltyFSM.choosing_user)

@router.callback_query(F.data.startswith("penalty_user_"))
async def penalty_choose_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[2])
    await state.update_data(user_id=user_id)
    await callback.message.edit_text("💸 Введите сумму штрафа (в рублях):")
    await state.set_state(PenaltyFSM.entering_amount)

@router.message(PenaltyFSM.entering_amount)
async def penalty_enter_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❗ Введите положительное число.")
        return

    await state.update_data(amount=amount)
    await message.answer("📝 Укажите причину штрафа:")
    await state.set_state(PenaltyFSM.entering_reason)

@router.message(PenaltyFSM.entering_reason)
async def penalty_enter_reason(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = data["user_id"]
    amount = data["amount"]
    reason = message.text.strip()

    # === уменьшаем ЗП (правильный порядок аргументов) ===
    ok = update_salary(user_id=user_id, value=-amount)
    if not ok:
        await message.answer("❗ Произошла ошибка при применении штрафа в БД. Проверь логи.")
        await state.clear()
        return

    # === уведомляем пользователя ===
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🚫 <b>Штраф начислен</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 <b>Сумма:</b> -{amount} ₽\n"
                f"📄 <b>Причина:</b> {reason}\n\n"
                "⚠️ <i>При несогласии свяжитесь с администратором.</i>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"Не удалось уведомить пользователя {user_id}: {e}")

    await message.answer(
        f"✅ Штраф успешно применён!\n"
        f"👤 Пользователь ID: {user_id}\n"
        f"💰 Сумма: -{amount} ₽\n"
        f"📄 Причина: {reason}"
    )

    await state.clear()

@router.message(F.text == "➕ Добавить задачу водителю", F.from_user.id.in_(ADMINS))
async def add_driver_task_start(message: types.Message, state: FSMContext):
    addresses = get_all_addresses()
    if not addresses:
        await message.answer("❌ Адресов пока нет. Сначала добавьте адрес.", reply_markup=admin_kb())
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"drv_addr_{addr_id}")]
            for addr_id, title in addresses
        ]
    )

    await message.answer("📍 Выберите адрес для задачи водителю:", reply_markup=kb)
    await state.set_state(DriverTaskCreate.waiting_address)


# === ВЫБОР АДРЕСА ===
@router.callback_query(F.data.regexp(r"^drv_addr_\d+$"))
async def driver_address_selected(callback: types.CallbackQuery, state: FSMContext):
    addr_id = int(callback.data.split("_")[2])
    await state.update_data(address_id=addr_id)

    await callback.message.answer(
        "✍️ Напишите, <b>что нужно привезти / сделать</b>:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(DriverTaskCreate.waiting_title)
    await callback.answer()


# === ВВОД НАЗВАНИЯ ===
@router.message(DriverTaskCreate.waiting_title, F.from_user.id.in_(ADMINS))
async def driver_task_title_entered(message: types.Message, state: FSMContext):
    await state.update_data(task_name=message.text.strip())
    await message.answer("🔐 Введите <b>код сейфа</b> (или '-' если не нужен):", parse_mode="HTML")
    await state.set_state(DriverTaskCreate.waiting_safe_code)


# === ВВОД КОДА СЕЙФА ===
@router.message(DriverTaskCreate.waiting_safe_code, F.from_user.id.in_(ADMINS))
async def driver_task_safe_entered(message: types.Message, state: FSMContext):
    safe_code = message.text.strip()
    if safe_code == "-":
        safe_code = ""
    await state.update_data(safe_code=safe_code)
    await message.answer("💬 Введите <b>комментарий</b> (или '-' если не нужен):", parse_mode="HTML")
    await state.set_state(DriverTaskCreate.waiting_comment)


# === ВВОД КОММЕНТАРИЯ И СОХРАНЕНИЕ ===
@router.message(DriverTaskCreate.waiting_comment, F.from_user.id.in_(ADMINS))
async def driver_task_comment_entered(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    data = await state.get_data()
    address_id = data.get("address_id")
    task_name = data.get("task_name")
    safe_code = data.get("safe_code")

    addr = get_address_by_id(address_id)
    address_title = addr[1] if addr else "Без адреса"

    # сохраняем задачу в таблицу driver_tasks
    add_driver_task(task_name, address_title, safe_code, comment)

    await message.answer(
        f"✅ Задача для <b>водителя</b> успешно добавлена!\n\n"
        f"🏠 Адрес: {address_title}\n"
        f"📦 Что привезти / сделать: {task_name}\n"
        f"🔐 Сейф: {safe_code or '—'}\n"
        f"💬 Комментарий: {comment or '—'}",
        parse_mode="HTML",
        reply_markup=admin_kb()
    )

    await state.clear()


@router.message(lambda m: m.text == "⬅️ Назад в меню")
async def back_to_main(message: types.Message):
    await message.answer("Вы вернулись в главное меню 👇", reply_markup=main_kb())

