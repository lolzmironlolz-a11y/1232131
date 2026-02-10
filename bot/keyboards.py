from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🆘 Помощь"), KeyboardButton(text="📋 Задачи")],
            [KeyboardButton(text="ℹ️ Как пользоваться ботом"), KeyboardButton(text="🧹 Что входит в уборку")],
            [KeyboardButton(text="🧽 Лайфхаки"), KeyboardButton(text='🎯 Бонусы и штрафы')], # 🆕 новая кнопка
            [KeyboardButton(text="📜 Политика использования"), KeyboardButton(text="❓ F.A.Q — Запрещено")],
            [KeyboardButton(text='🚚 Маршрут водителя')]
        ],
        resize_keyboard=True
    )
    return kb

kb_contact = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Поделиться контактом", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

def back_broadcast_kb():
    return types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [types.KeyboardButton(text="🔙 Назад")]
        ]
    )

def admin_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить задачу"),KeyboardButton(text='➕ Добавить адрес')],
            [KeyboardButton(text="🗑 Очистить выполненные"),KeyboardButton(text="✅ Выполненные задачи")],
            [KeyboardButton(text="🔍 Найти пользователя"),KeyboardButton(text='❌ Удалить пользователя')],
            [KeyboardButton(text="📉 Удалить бонусы"),KeyboardButton(text="➕ Добавить бонус")],
            [KeyboardButton(text='🗑 Удалить адрес'),KeyboardButton(text='🗑 Удалить задачи')],
            [KeyboardButton(text="💰 Обнулить ЗП"),KeyboardButton(text='📊 Посмотреть ЗП всех')],
            [KeyboardButton(text='ℹ️ Навигация админ-панели'), KeyboardButton(text='📖 Admin F.A.Q.')],
            [KeyboardButton(text='📢 Сообщение всем'),KeyboardButton(text='👑 Назначить должность')],
            [KeyboardButton(text="📅 Все уборки"),KeyboardButton(text='👥 Все пользователи')],
            [KeyboardButton(text="🚫 Штраф"),KeyboardButton(text="➕ Добавить задачу водителю")],
            [KeyboardButton(text="⬅️ Назад в меню")]

        ],
        resize_keyboard=True
    )
    return kb

def admin_nav_docs_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Как добавить задачу", callback_data="doc_add_task")],
        [InlineKeyboardButton(text="🏠 Как добавить адрес", callback_data="doc_add_address")],
        [InlineKeyboardButton(text="👤 Работа с пользователями", callback_data="doc_users")],
        [InlineKeyboardButton(text="💰 Работа с финансами", callback_data="doc_finance")],
        [InlineKeyboardButton(text="⬅️ Назад к навигации", callback_data="doc_back")]
    ])
    return kb




