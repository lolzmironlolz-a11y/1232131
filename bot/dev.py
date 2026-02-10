from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import sqlite3
import logging
from bot.config import DB_PATH, DEV_ID
from aiogram.types import FSInputFile

from bot.states import DevNotify

dev_router = Router()

def is_dev(user_id: int) -> bool:
    return user_id == DEV_ID


# === Главное меню Dev Panel ===
@dev_router.message(F.text == "/dev")
async def dev_panel(message: types.Message):
    if not is_dev(message.from_user.id):
        return await message.answer("🚫 Доступ запрещён.")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📌 FSM State", callback_data="dev_state")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="dev_users")],
            [InlineKeyboardButton(text="🗑 Сбросить бота", callback_data="dev_reset")],
            [InlineKeyboardButton(text="📂 Скачать логи", callback_data="dev_logs")],
            [InlineKeyboardButton(text="📨 Сообщение администрации", callback_data="dev_notify_admins")]

        ]
    )

    await message.answer("⚙️ <b>Developer Panel</b>", parse_mode="HTML", reply_markup=kb)


# === FSM State ===
@dev_router.callback_query(F.data == "dev_state")
async def dev_state(callback: types.CallbackQuery, state: FSMContext):
    s = await state.get_state()
    await callback.message.answer(f"📌 FSM State: <code>{s}</code>", parse_mode="HTML")

@dev_router.callback_query(F.data == "dev_logs")
async def dev_logs(callback: types.CallbackQuery):
    if not is_dev(callback.from_user.id):
        return await callback.message.answer("🚫 Доступ запрещён.")

    log_file = "bot.log"
    try:
        file = FSInputFile(log_file)
        await callback.message.answer_document(file, caption="📂 Вот логи бота:")
    except FileNotFoundError:
        await callback.message.answer("❌ Файл логов не найден.")

# === Пользователи ===
@dev_router.callback_query(F.data == "dev_users")
async def dev_users(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    await callback.message.answer(f"👥 Всего пользователей: {count}")


# === Сброс бота — первый шаг (спросить подтверждение) ===
@dev_router.callback_query(F.data == "dev_reset")
async def dev_reset_confirm(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, сбросить", callback_data="dev_reset_confirmed"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="dev_cancel")
            ]
        ]
    )
    await callback.message.answer(
        "⚠️ <b>Внимание!</b>\n\n"
        "Ты собираешься полностью очистить базу:\n"
        "— Пользователи 👥\n"
        "— Задачи 📋\n"
        "— Адреса 🏠\n"
        "— Статистика 💰\n\n"
        "Это действие <b>НЕОБРАТИМО</b>!\n\n"
        "Продолжить?",
        parse_mode="HTML",
        reply_markup=kb
    )


# === Сброс бота — подтверждение ===
@dev_router.callback_query(F.data == "dev_reset_confirmed")
async def dev_reset(callback: types.CallbackQuery):
    if not is_dev(callback.from_user.id):
        return await callback.message.answer("🚫 Доступ запрещён.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users")
        cur.execute("DELETE FROM tasks")
        cur.execute("DELETE FROM addresses")
        cur.execute("DELETE FROM user_stats")
        conn.commit()
        msg = "✅ База очищена. Бот сброшен к начальному состоянию."
        logging.warning("⚠️ Выполнен полный сброс базы через Dev Panel")
    except Exception as e:
        msg = f"❌ Ошибка сброса: {e}"
    finally:
        conn.close()

    await callback.message.answer(msg)


# === Отмена сброса ===
@dev_router.callback_query(F.data == "dev_cancel")
async def dev_cancel(callback: types.CallbackQuery):
    await callback.message.answer("❌ Сброс отменён.")

@dev_router.callback_query(F.data == "dev_notify_admins")
async def dev_notify_admins(callback: types.CallbackQuery, state: FSMContext):
    if not is_dev(callback.from_user.id):
        return await callback.message.answer("🚫 Доступ запрещён.")

    await state.set_state(DevNotify.waiting_text)
    await callback.message.answer("✍️ Введите текст сообщения, которое будет отправлено всей администрации (admins + managers).")

@dev_router.message(DevNotify.waiting_text)
async def dev_send_admins(message: types.Message, state: FSMContext):
    text = message.text.strip()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # берем пользователей с rank = 'admin' или 'manager'
    cur.execute("SELECT user_id FROM users WHERE rank IN ('admin', 'manager')")
    admins = cur.fetchall()
    conn.close()

    if not admins:
        await message.answer("❌ Администраторов и менеджеров не найдено.")
        await state.clear()
        return

    sent = 0
    for (user_id,) in admins:
        try:
            await message.bot.send_message(
                user_id,
                f"📨 <b>Сообщение от Разработчика</b>\n\n{text}",
                parse_mode="HTML"
            )
            sent += 1
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение {user_id}: {e}")

    await message.answer(f"✅ Сообщение отправлено {sent} сотрудникам администрацией.")
    await state.clear()
