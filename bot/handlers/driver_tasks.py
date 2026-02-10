from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from bot.db import (
    get_driver_tasks,
    get_driver_task_by_id,
    assign_driver_to_task,
    mark_driver_task_done,
    add_driver_task, get_address_by_title
)
from bot.db import get_user
from bot.config import ADMINS
from bot.keyboards import main_kb, admin_kb
import sqlite3
import logging

router = Router()
logging.basicConfig(level=logging.INFO)


# === Показ списка задач водителя ===
@router.message(F.text == "🚚 Маршрут водителя")
async def show_driver_tasks(message: types.Message):
    tasks = get_driver_tasks()
    if not tasks:
        await message.answer("❌ Задач для водителя пока нет.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{address} | {task_name}",
                    callback_data=f"drv_take_{task_id}"
                )
            ]
            for task_id, address, task_name, safe_code, comment, executor_id in tasks
        ]
    )

    await message.answer(
        "📋 <b>Доступные задачи для водителя:</b>\n\n"
        "Выберите маршрут, чтобы приступить.",
        parse_mode="HTML",
        reply_markup=kb
    )


# === Взять задачу ===
@router.callback_query(F.data.startswith("drv_take_"))
async def take_driver_task(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])
    task = get_driver_task_by_id(task_id)

    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    tid, address, task_name, safe_code, comment, executor_id = task

    # Если уже назначен другой водитель
    if executor_id and executor_id != callback.from_user.id:
        await callback.answer("🚫 Эта задача уже занята другим водителем.", show_alert=True)
        return

    # Назначаем текущего пользователя
    assign_driver_to_task(tid, callback.from_user.id)

    # получаем квартиру и этаж по адресу
    addr_info = get_address_by_title(address)  # (id, title, floor, apartment, description)
    floor = addr_info[2] if addr_info else "—"
    apartment = addr_info[3] if addr_info else "—"

    msg = (
        f"✅ <b>Задача взята в работу!</b>\n\n"
        f"🏠 <b>Адрес:</b> {address}, кв. {apartment} (этаж {floor})\n"
        f"🔐 <b>Сейф:</b> {safe_code or '—'}\n"
        f"📋 <b>Что сделать:</b> {task_name}\n"
    )
    if comment:
        msg += f"💬 <b>Комментарий:</b> {comment}\n"

    await state.update_data(task_id=tid, address=address, task_name=task_name)
    await callback.message.answer(msg, parse_mode="HTML")

    await callback.message.answer(
        "Когда всё сделаете — нажмите кнопку ниже 👇",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить задачу", callback_data=f"drv_done_{tid}")]]
        ),
    )
    await callback.answer()


# === Завершение задачи ===
@router.callback_query(F.data.startswith("drv_done_"))
async def complete_driver_task(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])
    data = await state.get_data()

    address = data.get("address", "—")
    task_name = data.get("task_name", "—")

    mark_driver_task_done(callback.from_user.id, task_id, task_name, address)

    user = get_user(callback.from_user.id)
    fio = user[1] if user else callback.from_user.full_name

    # Уведомляем админов
    for admin_id in ADMINS:
        try:
            await callback.bot.send_message(
                admin_id,
                (
                    f"✅ <b>Водитель завершил задачу!</b>\n\n"
                    f"👤 <b>{fio}</b>\n"
                    f"🏠 <b>Адрес:</b> {address}\n"
                    f"🧾 <b>Задача:</b> {task_name}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"Ошибка при уведомлении администратора {admin_id}: {e}")

    await callback.message.answer(
        "🎉 Задача успешно завершена!\nОтличная работа 🚚",
        reply_markup=main_kb()
    )
    await state.clear()
    await callback.answer()