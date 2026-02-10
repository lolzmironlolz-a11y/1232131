import json
import sqlite3

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from aiogram.filters import Command
from datetime import datetime

from bot.config import DB_PATH
from bot.db import get_user_rank, get_done_tasks, get_done_task_details  # добавим нужные функции из db

router = Router()

# ====== Команда входа в менеджерскую панель ======
@router.message(Command("manager"))
async def manager_panel(message: types.Message):
    user_id = message.from_user.id
    rank = get_user_rank(user_id)  # получаем должность пользователя

    if rank != "manager":
        await message.answer("🚫 У вас нет доступа к менеджерской панели.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполненные задачи", callback_data="manager_done_tasks")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="manager_close")]
    ])

    await message.answer("📋 <b>Менеджерская панель</b>\nВыберите действие:", reply_markup=kb, parse_mode="HTML")


# ====== Обработка кнопки "Выполненные задачи" ======
@router.callback_query(F.data.startswith("manager_done_tasks"))
async def manager_show_completed_tasks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    rank = get_user_rank(user_id)
    if rank != "manager":
        await callback.answer("🚫 Нет доступа", show_alert=True)
        return

    # Получаем номер страницы
    parts = callback.data.split(":")
    page = int(parts[1]) if len(parts) > 1 else 0

    rows = get_done_tasks()
    if not rows:
        await callback.message.answer("✅ Нет выполненных задач.")
        return

    PAGE_SIZE = 10
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_rows = rows[start:end]

    kb_buttons = []

    for done_id, address, fio, completed_at in page_rows:
        text = f"{address} — {datetime.fromisoformat(completed_at).strftime('%d.%m %H:%M')} ({fio})"
        kb_buttons.append([InlineKeyboardButton(text=text[:60], callback_data=f"manager_done_{done_id}")])

    nav_buttons = []

    # Назад
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"manager_done_tasks:{page-1}"))

    # Вперёд
    if end < len(rows):
        nav_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"manager_done_tasks:{page+1}"))

    if nav_buttons:
        kb_buttons.append(nav_buttons)

    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    if callback.message.text.startswith("📋 Выполненные"):
        await callback.message.edit_reply_markup(kb)
    else:
        await callback.message.answer("📋 Выполненные задачи:", reply_markup=kb)


# ====== Детали выполненной задачи ======
@router.callback_query(F.data.startswith("manager_done_"))
async def manager_show_done_task_details(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    rank = get_user_rank(user_id)

    if rank != "manager":
        await callback.answer("🚫 Нет доступа", show_alert=True)
        return

    done_task_id = int(callback.data.split("_")[2])
    done_task = get_done_task_details(done_task_id)
    if not done_task:
        await callback.message.answer("❌ Задача не найдена.")
        return

    user_id, address, fio, photos_json, videos_json, missing_text, completed_at, description, breakage_photos, breakage_videos = done_task

    text = (
        f"✅ <b>Выполненная задача</b>\n\n"
        f"🏠 <b>Адрес:</b> {address}\n"
        f"👤 <b>Исполнитель:</b> {fio}\n"
        f"📝 <b>Описание:</b> {description or '—'}\n"
        f"⏰ <b>Выполнена:</b> {datetime.fromisoformat(completed_at).strftime('%d.%m.%Y %H:%M')}"
    )
    if missing_text:
        text += f"\n💬 <b>Чего не хватает на квартире:</b> {missing_text}"

    photos = photos_json or []
    videos = videos_json or []

    # Отправляем медиа
    media_list = []
    for i, p in enumerate(photos):
        media_list.append(InputMediaPhoto(media=p, caption="📸 Подтверждение уборки" if i == 0 else None))
    for i, v in enumerate(videos):
        media_list.append(InputMediaVideo(media=v, caption="📹 Подтверждение уборки" if not media_list else None))

    if media_list:
        await callback.message.answer_media_group(media_list)
    else:
        await callback.message.answer("✅ Нет фото/видео подтверждения уборки.")

    # Кнопки: просмотр поломок и назад
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Поломки", callback_data=f"manager_breakages_{done_task_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="manager_done_tasks")]
        ]
    )

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("manager_breakages_"))
async def manager_show_breakages(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    rank = get_user_rank(user_id)

    if rank != "manager":
        await callback.answer("🚫 Нет доступа", show_alert=True)
        return

    done_task_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT breakage_photos, breakage_videos
        FROM done_tasks
        WHERE id = ?
    """, (done_task_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await callback.message.answer("❌ Нет данных о поломках.")
        return

    break_photos = json.loads(row[0] or '[]')
    break_videos = json.loads(row[1] or '[]')

    if not break_photos and not break_videos:
        await callback.message.answer("✅ Поломок не обнаружено.")
        return

    media_list = []
    for p in break_photos:
        media_list.append(InputMediaPhoto(media=p))
    for v in break_videos:
        media_list.append(InputMediaVideo(media=v))

    await callback.message.answer("🔧 <b>Фото/видео поломок:</b>", parse_mode="HTML")
    if media_list:
        await callback.message.answer_media_group(media_list)



# ====== Закрыть панель ======
@router.callback_query(F.data == "manager_close")
async def manager_close(callback: types.CallbackQuery):
    await callback.message.delete()