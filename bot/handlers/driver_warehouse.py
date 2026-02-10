from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
import sqlite3
import json
from datetime import datetime
from bot.config import DB_PATH, ADMINS

router = Router()

# ======================= ФУНКЦИИ ДОСТУПА ============================
def is_driver_warehouse(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT rank FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row and row[0] == "driver_warehouse"


# ================== ОСНОВНОЙ УНИВЕРСАЛЬНЫЙ МЕТОД ====================
async def _show_completed_tasks_generic(message_or_cb, state: FSMContext):
    """Общая функция: выводит список адресов с выполненными задачами"""
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
        await message_or_cb.answer("✅ Нет выполненных задач.")
        return

    addresses = {}
    for done_id, addr_text, title, floor, apartment, completed_at, fio in rows:
        addr_name = (
            f"{title}, этаж {floor}, кв. {apartment}"
            if title else (addr_text or "❓ Неизвестный адрес")
        )
        addresses.setdefault(addr_name, []).append((done_id, fio, completed_at))

    await state.update_data(done_tasks_map=addresses)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏠 {addr}", callback_data=f"addr_done_{i}")]
            for i, addr in enumerate(addresses.keys())
        ]
    )

    await message_or_cb.answer("📁 Выберите адрес:", reply_markup=kb)


async def _show_tasks_for_address(callback, state: FSMContext):
    """Общая функция — показывает выполненные задачи по адресу"""
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
        ] + [
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_done_list")]
        ]
    )

    await callback.message.edit_text(
        f"📋 <b>{address_name}</b>\nВыберите выполненную задачу:",
        parse_mode="HTML",
        reply_markup=kb
    )


async def _show_one_done_task(callback, done_task_id):
    """Общая функция — показывает детали одной выполненной задачи"""

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, addr_id, fio, photos, videos, missing_text,
               completed_at, description, breakage_photos, breakage_videos
        FROM done_tasks WHERE id = ?
    """, (done_task_id,))
    row = cur.fetchone()

    if not row:
        await callback.message.edit_text("❌ Задача не найдена.")
        return

    user_id, addr_id, fio, photos_json, videos_json, missing_text, completed_at, description, breakage_photos, breakage_videos = row

    # Получение адреса
    cur.execute("SELECT title, floor, apartment FROM addresses WHERE id = ?", (addr_id,))
    a = cur.fetchone()
    if a:
        address = f"{a[0]}, этаж {a[1]}, кв. {a[2]}"
    else:
        cur.execute("SELECT address FROM done_tasks WHERE id = ?", (done_task_id,))
        ad = cur.fetchone()
        address = ad[0] if ad and ad[0] else "❓ Неизвестный адрес"

    conn.close()

    # текст
    text = (
        f"✅ <b>Выполненная задача</b>\n\n"
        f"🏠 <b>Адрес:</b> {address}\n"
        f"👤 <b>Исполнитель:</b> {fio}\n"
        f"📝 <b>Описание:</b> {description or '—'}\n"
        f"⏰ <b>Выполнена:</b> {datetime.fromisoformat(completed_at).strftime('%d.%m.%Y %H:%M')}"
    )

    if missing_text:
        text += f"\n💬 <b>Чего не хватает:</b> {missing_text}"

    # медиа
    def parse(x):
        if not x:
            return []
        try:
            return json.loads(x)
        except:
            return []

    photos = parse(photos_json)
    videos = parse(videos_json)

    media = []
    media += [InputMediaPhoto(media=p) for p in photos]
    media += [InputMediaVideo(media=v) for v in videos]

    if media:
        for i in range(0, len(media), 10):
            await callback.message.answer_media_group(media[i:i + 10])

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Поломки", callback_data=f"breakages_{done_task_id}")],
            [InlineKeyboardButton(text="📄 Остатки", callback_data=f"remaining_{done_task_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_done_list")]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ===================== ДЛЯ ВОДИТЕЛЕЙ СКЛАДА (/tasks) ======================

@router.message(Command("tasks"))
async def tasks_driver(message: types.Message, state: FSMContext):
    if not is_driver_warehouse(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return

    await _show_completed_tasks_generic(message, state)


@router.callback_query(F.data.startswith("addr_done_"))
async def tasks_driver_addr(callback: types.CallbackQuery, state: FSMContext):
    if not is_driver_warehouse(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа", show_alert=True)

    await _show_tasks_for_address(callback, state)


@router.callback_query(F.data.startswith("done_"))
async def tasks_driver_one(callback: types.CallbackQuery):
    if not is_driver_warehouse(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа", show_alert=True)

    await _show_one_done_task(callback, int(callback.data.split("_")[1]))


@router.callback_query(F.data == "back_to_done_list")
async def tasks_driver_back(callback: types.CallbackQuery, state: FSMContext):
    if not is_driver_warehouse(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа", show_alert=True)

    data = await state.get_data()
    addresses = data.get("done_tasks_map", {})

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏠 {addr}", callback_data=f"addr_done_{i}")]
            for i, addr in enumerate(addresses.keys())
        ]
    )

    await callback.message.edit_text("📁 Выберите адрес:", reply_markup=kb)


# =========================== ДЛЯ АДМИНОВ ==============================

@router.message(F.text == "✅ Выполненные задачи", F.from_user.id.in_(ADMINS))
async def tasks_admin(message: types.Message, state: FSMContext):
    await _show_completed_tasks_generic(message, state)


@router.callback_query(F.data.startswith("addr_done_"), F.from_user.id.in_(ADMINS))
async def tasks_admin_addr(callback: types.CallbackQuery, state: FSMContext):
    await _show_tasks_for_address(callback, state)


@router.callback_query(F.data.startswith("done_"), F.from_user.id.in_(ADMINS))
async def tasks_admin_one(callback: types.CallbackQuery):
    await _show_one_done_task(callback, int(callback.data.split("_")[1]))


@router.callback_query(F.data == "back_to_done_list", F.from_user.id.in_(ADMINS))
async def tasks_admin_back(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    addresses = data.get("done_tasks_map", {})

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏠 {addr}", callback_data=f"addr_done_{i}")]
            for i, addr in enumerate(addresses.keys())
        ]
    )

    await callback.message.edit_text("📁 Выберите адрес:", reply_markup=kb)


# ======================== ПОЛОМКИ / ОСТАТКИ ===========================

@router.callback_query(F.data.startswith("breakages_"))
async def breakages(callback: types.CallbackQuery):
    done_task_id = int(callback.data.split("_")[1])

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT breakage_photos, breakage_videos FROM done_tasks WHERE id = ?", (done_task_id,))
    row = cur.fetchone()
    conn.close()

    def parse(x):
        try:
            return json.loads(x or "[]")
        except:
            return []

    photos = parse(row[0]) if row else []
    videos = parse(row[1]) if row else []

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"done_{done_task_id}")]])

    if not photos and not videos:
        await callback.message.edit_text("🔧 Поломок нет.", reply_markup=kb)
        return

    await callback.message.answer_media_group(
        [InputMediaPhoto(media=p) for p in photos] +
        [InputMediaVideo(media=v) for v in videos]
    )

    await callback.message.edit_text("🔧 Поломки:", reply_markup=kb)


@router.callback_query(F.data.startswith("remaining_"))
async def remaining(callback: types.CallbackQuery):
    done_task_id = int(callback.data.split("_")[1])

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT remaining_photos FROM done_tasks WHERE id = ?", (done_task_id,))
    row = cur.fetchone()
    conn.close()

    def parse(x):
        try:
            return json.loads(x or "[]")
        except:
            return []

    photos = parse(row[0]) if row else []

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"done_{done_task_id}")]])

    if not photos:
        await callback.message.edit_text("📄 Остатков нет.", reply_markup=kb)
        return

    await callback.message.answer_media_group([InputMediaPhoto(media=p) for p in photos])
    await callback.message.edit_text("📄 Остатки:", reply_markup=kb)
