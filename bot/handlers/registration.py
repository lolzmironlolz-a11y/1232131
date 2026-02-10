from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from datetime import datetime

from bot.db import (
    save_partial_contact,
    save_full_profile,
    is_registered,
    add_or_update_user,
    add_bonus  # ⚠️ нужно добавить функцию для бонусов (ниже покажу)
)
from bot.keyboards import kb_contact, main_kb
from bot.states import RegStates

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    username = message.from_user.username or None

    # ⚠️ Обновляем только username, не трогаем ФИО
    add_or_update_user(uid, None, username)

    if is_registered(uid):
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Этот бот создан, чтобы ты легко находил задачи и зарабатывал бонусы 💰.\n\n"
            "📌 Просто выбирай задачу ниже, выполняй её и получай вознаграждение.\n"
            "Всё максимально просто и удобно 🚀",
            reply_markup=main_kb()
        )
        return

    await message.answer("Привет! Для регистрации пришли контакт:", reply_markup=kb_contact)
    await state.set_state(RegStates.waiting_contact)


@router.message(RegStates.waiting_contact, F.content_type == "contact")
async def contact_handler(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    uid = message.from_user.id
    save_partial_contact(uid, phone)
    await message.answer("Теперь напиши своё ФИО:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegStates.waiting_fio)


@router.message(RegStates.waiting_fio)
async def fio_handler(message: types.Message, state: FSMContext):
    fio = message.text.strip()
    await state.update_data(fio=fio)
    await message.answer("Напиши район проживания:")
    await state.set_state(RegStates.waiting_district)


@router.message(RegStates.waiting_district)
async def district_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id
    fio = data["fio"]
    district = message.text.strip()
    reg_date = datetime.now().strftime("%Y-%m-%d")  # 🕒 Дата регистрации

    # Сохраняем профиль вместе с датой
    save_full_profile(uid, fio, district, reg_date)

    # Начисляем бонусы
    add_bonus(uid, 50)

    await state.clear()

    reg_complete_text = (
        "🎉 <b>Регистрация завершена!</b>\n\n"
        f"📅 <b>Дата регистрации:</b> {reg_date}\n"
        f"💰 <b>Бонус начислен:</b> +50 единиц\n\n"
        "Теперь у вас открыт полный доступ к возможностям бота:\n"
        "📌 Получать и выполнять задачи\n"
        "💰 Зарабатывать и получать бонусы\n"
        "📝 Следить за своим прогрессом и историей задач\n\n"
        "⚠️ Перед тем как приступить к уборкам и работе через бот, "
        "обязательно ознакомьтесь с:\n"
        "🔹 <b>❓ F.A.Q — Запрещено</b>\n"
        "🔹 <b>Политикой использования</b>\n\n"
        "❓ Если что-то останется непонятным — нажмите на кнопку <b>Помощь</b>."
    )

    await message.answer(reg_complete_text, reply_markup=main_kb(), parse_mode="HTML")
