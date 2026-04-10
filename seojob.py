"""
ПОЛНЫЙ КЛОН @jobseo_bot
Версия: 3.0 (aiogram 3.x)
Функционал:
- Личный кабинет со статистикой
- SeoCoin (внутренняя валюта)
- ТОП по SeoCoin
- Задания с геолокацией
- Реферальная система (2 уровня: 20% и 5%)
- Вывод средств (ЮMoney, CryptoBot, Т-Банк, СБЕР, телефон)
- Админ-панель: рассылка, выдача/списание монет, выплаты, задания
- Хранение в JSON
Кодил бота @info_dsn
"""

import asyncio
import logging
import json
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from contextlib import suppress

# Установка зависимостей:
# pip install aiogram aiohttp

import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, Message, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# ============================ КОНФИГУРАЦИЯ ============================
BOT_TOKEN = "сюда токен бота"  # вставь свой токен
ADMIN_IDS = [айдишку сюда]  # Айди админов

# Ссылки для конфига
CHANNEL_LINK = "https://t.me/jobseo_channel"
CHAT_LINK = "https://t.me/jobseo_chat"
REVIEWS_LINK = "https://t.me/jobseo_reviews"
SUPPORT_LINK = "https://t.me/jobseo_support"
FAQ_LINK = "https://telegra.ph/FAQ-JobSeo-Bot-01-01"
EXTRA_TASKS_CHAT = "https://t.me/Seo_Task"

# Платежные системы
PAYMENT_SYSTEMS = {
    "yoo": "YooMoney",
    "crypto": "CryptoBot",
    "tbank": "Т-Банк",
    "sber": "СБЕР",
    "phone": "На баланс телефона"
}

# Настройки валюты
SEOCOIN_PER_DAY_USERNAME = 5

# Файлы для хранения данных
USERS_FILE = "users.json"
TASKS_FILE = "tasks.json"
WITHDRAWALS_FILE = "withdrawals.json"

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================ FSM СОСТОЯНИЯ ============================
class WithdrawalStates(StatesGroup):
    choosing_system = State()
    entering_phone = State()
    entering_account = State()
    entering_amount = State()
    confirming = State()

class TaskStates(StatesGroup):
    waiting_city = State()
    waiting_task_action = State()
    waiting_task_proof = State()

class AdminStates(StatesGroup):
    mailing_message = State()
    add_seocoin_user = State()
    add_seocoin_amount = State()
    remove_seocoin_user = State()
    remove_seocoin_amount = State()
    create_task_title = State()
    create_task_desc = State()
    create_task_reward = State()
    create_task_city = State()
    create_task_instructions = State()
    find_user_id = State()

# ============================ КЛАССЫ ДАННЫХ ============================
class JSONStorage:
    """Базовый класс для работы с JSON"""
    
    @staticmethod
    def _read(file_path: str) -> Dict:
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    @staticmethod
    def _write(file_path: str, data: Dict):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

class UserManager(JSONStorage):
    """Управление пользователями"""
    
    @classmethod
    def get_user(cls, user_id: int, username: str = None, full_name: str = None, referrer_id: int = None) -> Dict:
        """Получить пользователя или создать нового"""
        data = cls._read(USERS_FILE)
        user_id_str = str(user_id)
        
        if user_id_str not in data:
            # Новый пользователь
            data[user_id_str] = {
                "id": user_id,
                "username": username,
                "full_name": full_name,
                "status": "user",
                "registered_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "balance": 0.0,
                "seocoin": 0,
                "seocoin_weekly": 0,
                "total_earned": 0.0,
                "tasks_completed": 0,
                "city": None,
                "referrer_id": str(referrer_id) if referrer_id else None,
                "referrals_1": [],
                "referrals_2": [],
                "referral_earnings": 0.0,
                "completed_tasks": [],
                "withdrawals": [],
                "last_username_check": None
            }
            
            # Обработка реферала
            if referrer_id and str(referrer_id) in data:
                # Добавляем реферала 1 уровня
                data[str(referrer_id)]["referrals_1"].append(user_id_str)
                
                # Проверяем реферера 2 уровня
                referrer_2 = data[str(referrer_id)].get("referrer_id")
                if referrer_2 and referrer_2 in data:
                    data[referrer_2]["referrals_2"].append(user_id_str)
            
            cls._write(USERS_FILE, data)
        else:
            # Обновляем данные
            if username:
                data[user_id_str]["username"] = username
            if full_name:
                data[user_id_str]["full_name"] = full_name
            data[user_id_str]["last_activity"] = datetime.now().isoformat()
            cls._write(USERS_FILE, data)
        
        return data[user_id_str]
    
    @classmethod
    def update_user(cls, user_id: int, **kwargs):
        """Обновить данные пользователя"""
        data = cls._read(USERS_FILE)
        user_id_str = str(user_id)
        if user_id_str in data:
            data[user_id_str].update(kwargs)
            data[user_id_str]["last_activity"] = datetime.now().isoformat()
            cls._write(USERS_FILE, data)
    
    @classmethod
    def add_seocoin(cls, user_id: int, amount: int):
        """Начислить SeoCoin"""
        data = cls._read(USERS_FILE)
        user_id_str = str(user_id)
        if user_id_str in data:
            data[user_id_str]["seocoin"] += amount
            data[user_id_str]["seocoin_weekly"] += amount
            cls._write(USERS_FILE, data)
            return True
        return False
    
    @classmethod
    def remove_seocoin(cls, user_id: int, amount: int):
        """Списать SeoCoin"""
        data = cls._read(USERS_FILE)
        user_id_str = str(user_id)
        if user_id_str in data and data[user_id_str]["seocoin"] >= amount:
            data[user_id_str]["seocoin"] -= amount
            data[user_id_str]["seocoin_weekly"] -= amount
            cls._write(USERS_FILE, data)
            return True
        return False
    
    @classmethod
    def add_balance(cls, user_id: int, amount: float):
        """Начислить рубли"""
        data = cls._read(USERS_FILE)
        user_id_str = str(user_id)
        if user_id_str in data:
            data[user_id_str]["balance"] += amount
            data[user_id_str]["total_earned"] += amount
            cls._write(USERS_FILE, data)
            return True
        return False
    
    @classmethod
    def process_task_completion(cls, user_id: int, task_reward: float):
        """Обработать выполнение задания и начислить реферальные бонусы"""
        data = cls._read(USERS_FILE)
        user_id_str = str(user_id)
        
        if user_id_str not in data:
            return
        
        # Начисляем награду пользователю
        data[user_id_str]["balance"] += task_reward
        data[user_id_str]["total_earned"] += task_reward
        data[user_id_str]["tasks_completed"] += 1
        
        # Реферальные начисления
        referrer_1_id = data[user_id_str].get("referrer_id")
        if referrer_1_id and referrer_1_id in data:
            # 20% рефереру 1 уровня
            amount_1 = task_reward * 0.2
            data[referrer_1_id]["balance"] += amount_1
            data[referrer_1_id]["total_earned"] += amount_1
            data[referrer_1_id]["referral_earnings"] += amount_1
            
            # Реферер 2 уровня
            referrer_2_id = data[referrer_1_id].get("referrer_id")
            if referrer_2_id and referrer_2_id in data:
                amount_2 = task_reward * 0.05
                data[referrer_2_id]["balance"] += amount_2
                data[referrer_2_id]["total_earned"] += amount_2
                data[referrer_2_id]["referral_earnings"] += amount_2
        
        cls._write(USERS_FILE, data)
    
    @classmethod
    def get_top_seocoin(cls, limit: int = 15) -> List[Tuple[str, int]]:
        """ТОП по SeoCoin"""
        data = cls._read(USERS_FILE)
        users = []
        for uid, uinfo in data.items():
            username = uinfo.get("username", f"id{uid}")
            if not username.startswith("@"):
                username = f"@{username}" if username else f"id{uid}"
            seocoin = uinfo.get("seocoin_weekly", 0)
            users.append((username, seocoin))
        
        users.sort(key=lambda x: x[1], reverse=True)
        return users[:limit]
    
    @classmethod
    def calculate_places(cls, user_id: int) -> Dict:
        """Рассчитать места пользователя в ТОПах"""
        data = cls._read(USERS_FILE)
        users_list = list(data.items())
        
        # Сортируем по разным критериям
        by_earnings = sorted(users_list, key=lambda x: x[1].get("total_earned", 0), reverse=True)
        by_seocoin = sorted(users_list, key=lambda x: x[1].get("seocoin", 0), reverse=True)
        by_referrals = sorted(users_list, key=lambda x: len(x[1].get("referrals_1", [])), reverse=True)
        by_ref_earnings = sorted(users_list, key=lambda x: x[1].get("referral_earnings", 0), reverse=True)
        
        user_id_str = str(user_id)
        
        def find_place(sorted_list, key):
            for i, (uid, _) in enumerate(sorted_list):
                if uid == user_id_str:
                    return i + 1
            return len(sorted_list) + 1
        
        return {
            "earnings": find_place(by_earnings, user_id_str),
            "seocoin": find_place(by_seocoin, user_id_str),
            "referrals_count": find_place(by_referrals, user_id_str),
            "referral_earnings": find_place(by_ref_earnings, user_id_str)
        }

class TaskManager(JSONStorage):
    """Управление заданиями"""
    
    @classmethod
    def create_task(cls, task_data: Dict) -> str:
        """Создать новое задание"""
        data = cls._read(TASKS_FILE)
        task_id = str(len(data) + 1)
        
        task = {
            "id": task_id,
            "title": task_data.get("title", "Без названия"),
            "description": task_data.get("description", ""),
            "reward": float(task_data.get("reward", 10)),
            "city": task_data.get("city"),
            "instructions": task_data.get("instructions", ""),
            "is_active": True,
            "created_at": datetime.now().isoformat(),
            "created_by": task_data.get("created_by"),
            "completed_by": []
        }
        
        data[task_id] = task
        cls._write(TASKS_FILE, data)
        return task_id
    
    @classmethod
    def get_available_tasks(cls, user_id: int, city: str = None) -> List[Dict]:
        """Получить доступные задания"""
        data = cls._read(TASKS_FILE)
        user_data = UserManager.get_user(user_id)
        completed = set(user_data.get("completed_tasks", []))
        
        available = []
        for tid, task in data.items():
            if not task.get("is_active", True):
                continue
            if tid in completed:
                continue
            if task.get("city") and city and task["city"].lower() != city.lower():
                continue
            available.append(task)
        
        return available
    
    @classmethod
    def complete_task(cls, user_id: int, task_id: str):
        """Отметить задание как выполненное"""
        data = cls._read(TASKS_FILE)
        if task_id not in data:
            return False
        
        user_id_str = str(user_id)
        if user_id_str in data[task_id].get("completed_by", []):
            return False
        
        if "completed_by" not in data[task_id]:
            data[task_id]["completed_by"] = []
        data[task_id]["completed_by"].append(user_id_str)
        cls._write(TASKS_FILE, data)
        
        # Обновляем пользователя
        user_data = UserManager.get_user(user_id)
        completed = user_data.get("completed_tasks", [])
        completed.append(task_id)
        UserManager.update_user(user_id, completed_tasks=completed)
        
        return True

class WithdrawalManager(JSONStorage):
    """Управление заявками на вывод"""
    
    @classmethod
    def create_request(cls, user_id: int, system: str, account: str, amount: float) -> str:
        """Создать заявку на вывод"""
        data = cls._read(WITHDRAWALS_FILE)
        req_id = str(len(data) + 1)
        
        request = {
            "id": req_id,
            "user_id": user_id,
            "system": system,
            "account": account,
            "amount": amount,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "processed_by": None,
            "processed_at": None
        }
        
        data[req_id] = request
        cls._write(WITHDRAWALS_FILE, data)
        
        # Обновляем пользователя
        user_data = UserManager.get_user(user_id)
        withdrawals = user_data.get("withdrawals", [])
        withdrawals.append(req_id)
        UserManager.update_user(user_id, withdrawals=withdrawals)
        
        return req_id
    
    @classmethod
    def get_pending_requests(cls) -> Dict:
        """Получить все ожидающие заявки"""
        data = cls._read(WITHDRAWALS_FILE)
        return {k: v for k, v in data.items() if v.get("status") == "pending"}
    
    @classmethod
    def process_request(cls, req_id: str, admin_id: int, approve: bool = True):
        """Обработать заявку (одобрить/отклонить)"""
        data = cls._read(WITHDRAWALS_FILE)
        if req_id not in data:
            return False
        
        data[req_id]["status"] = "approved" if approve else "rejected"
        data[req_id]["processed_by"] = admin_id
        data[req_id]["processed_at"] = datetime.now().isoformat()
        
        if approve:
            # Списываем баланс у пользователя
            user_id = data[req_id]["user_id"]
            amount = data[req_id]["amount"]
            user_data = UserManager.get_user(user_id)
            new_balance = user_data.get("balance", 0) - amount
            UserManager.update_user(user_id, balance=new_balance)
        
        cls._write(WITHDRAWALS_FILE, data)
        return True

# ============================ КНОПКИ И КЛАВИАТУРЫ ============================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню (Reply-кнопки)"""
    kb = [
        [KeyboardButton(text="✍️ Приступить к заданию")],
        [KeyboardButton(text="🖥 Личный кабинет"), KeyboardButton(text="💰 Вывод средств")],
        [KeyboardButton(text="🍀 Топ по SeoCoin"), KeyboardButton(text="🧑‍🤝‍🧑 Реферальная программа")],
        [KeyboardButton(text="📦 Доп. задания"), KeyboardButton(text="🛡 Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка отмены"""
    kb = [[KeyboardButton(text="🔙 Назад в меню")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_location_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка для геолокации"""
    kb = [
        [KeyboardButton(text="🌐 Отправить геолокацию", request_location=True)],
        [KeyboardButton(text="🔙 Назад в менюО")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_withdrawal_systems_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора платежной системы"""
    builder = InlineKeyboardBuilder()
    for code, name in PAYMENT_SYSTEMS.items():
        builder.button(text=name, callback_data=f"withdraw_sys:{code}")
    builder.button(text="« Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Админ-панель"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📨 Рассылка", callback_data="admin_mailing")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="➕ Выдать SeoCoin", callback_data="admin_add_seocoin")
    builder.button(text="➖ Забрать SeoCoin", callback_data="admin_remove_seocoin")
    builder.button(text="💰 Запросы на вывод", callback_data="admin_withdrawals")
    builder.button(text="🔍 Найти юзера", callback_data="admin_find_user")
    builder.button(text="📝 Создать задание", callback_data="admin_create_task")
    builder.adjust(2)
    return builder.as_markup()

def get_back_button() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    builder = InlineKeyboardBuilder()
    builder.button(text="« Назад", callback_data="back_to_main")
    return builder.as_markup()

# ============================ ХЭНДЛЕРЫ ============================

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ===== СТАРТ И РЕГИСТРАЦИЯ =====

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start с реферальной системой"""
    await state.clear()
    
    # Проверяем реферальный параметр
    referrer_id = None
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
            if referrer_id == message.from_user.id:
                referrer_id = None  # Нельзя рефералить самого себя
        except:
            pass
    
    # Регистрируем пользователя
    user = UserManager.get_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        referrer_id=referrer_id
    )
    
    # Приветствие
    welcome_text = (
        "👋 Добро пожаловать в JobSeo Bot!\n\n"
        "✍️ Чтобы начать задание нажмите кнопку «✍️ Приступить к заданию»\n"
        "🎁 Активные розыгрыши и акции \n"
        "📍 Напоминаем Вам, что если у Вас есть дополнительные аккаунты на площадках, то Вы всегда можете взять задания в нашем чате с готовыми отзывами - @Seo_Task\n"
        "⚠️  Чтобы не пропустить уведомления от бота о выполнении этапов НАСТОЯТЕЛЬНО РЕКОМЕНДУЕМ включить уведомления!\n"
        "💲 JobSeo - твой помошник в мире заработка\n\n"
        "👇 Выберите действие в меню ниже"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

# ===== ЛИЧНЫЙ КАБИНЕТ =====

@dp.message(F.text == "🖥 Личный кабинет")
async def show_profile(message: Message):
    """Показывает личный кабинет пользователя"""
    user_id = message.from_user.id
    user = UserManager.get_user(user_id)
    
    # Рассчитываем места в ТОПе
    places = UserManager.calculate_places(user_id)
    
    # Считаем дни с нами
    reg_date = datetime.fromisoformat(user.get("registered_at", datetime.now().isoformat()))
    days_with_us = (datetime.now() - reg_date).days
    
    # Формируем текст
    current_time = datetime.now().strftime("%H:%M:%S %d-%m-%Y")
    username = message.from_user.username or "нет"
    if username != "нет" and not username.startswith("@"):
        username = f"@{username}"
    
    status_emoji = "👤" if user.get("status") == "user" else "👑"
    
    profile_text = (
        f"🖥 Личный кабинет\n\n"
        f"⏱ Текущее время:\n"
        f"{current_time}\n\n"
        f"🆔 Ваш ID: {user_id}\n"
        f"⚜️ Ваш логин: {username}\n"
        f"💫 Ваш статус: {status_emoji} {user.get('status')}\n"
        f"🫂 Вы с нами: {days_with_us} дн.\n\n"
        f"⏳ Заданий на проверке: 0\n\n"
        f"💰 Текущий баланс: {user.get('balance', 0):.2f} ₽\n"
        f"☘️ Заработано SeoCoin за неделю: {user.get('seocoin_weekly', 0)}\n"
        f"🍀 Общий баланс SeoCoin: {user.get('seocoin', 0)}\n"
        f"🧾 Заработано за все время: {user.get('total_earned', 0):.2f} ₽\n"
        f"✍️ Заработано с заданий: {user.get('rewards_received', user.get('total_earned', 0)):.2f} ₽\n\n"
        f"— Приглашено рефералов 1 ур. - {len(user.get('referrals_1', []))}\n"
        f"— Приглашено рефералов 2 ур. - {len(user.get('referrals_2', []))}\n"
        f"🤝 Заработано с рефералов: {user.get('referral_earnings', 0):.1f} ₽\n\n"
        f"🔝 Ваше место в ТОПЕ:\n"
        f"├ по заработку #{places['earnings']}\n"
        f"├ по SeoCoin #{places['seocoin']}\n"
        f"├ по количеству рефералов #{places['referrals_count']}\n"
        f"└ по заработку с рефералов #{places['referral_earnings']}"
    )
    
    # Инлайн кнопки для соцсетей
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Канал", url=CHANNEL_LINK)
    builder.button(text="💬 Чат", url=CHAT_LINK)
    builder.button(text="📑 Отзывы", url=REVIEWS_LINK)
    builder.button(text="🛠 Поддержка", url=SUPPORT_LINK)
    builder.button(text="📊 Моя статистика", callback_data="my_stats")
    builder.adjust(2)
    
    await message.answer(profile_text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "my_stats")
async def my_stats_callback(callback: CallbackQuery):
    """Показывает детальную статистику"""
    user_id = callback.from_user.id
    user = UserManager.get_user(user_id)
    
    # Здесь можно добавить графики или детализацию по заданиям
    stats_text = (
        "📊 Детальная статистика:\n\n"
        f"✅ Выполнено заданий: {user.get('tasks_completed', 0)}\n"
        f"💰 Средний чек: {(user.get('total_earned', 0) / max(user.get('tasks_completed', 0), 1)):.2f} ₽\n"
        f"📈 Рейтинг выполнения: {(user.get('tasks_completed', 0) / 100):.1%}\n\n"
        "💡 Чтобы увеличить заработок:\n"
        "• Приглашайте рефералов\n"
        "• Добавьте @jobseo_bot в ник\n"
        "• Выполняйте задания ежедневно"
    )
    
    await callback.message.edit_text(stats_text, reply_markup=get_back_button())
    await callback.answer()

# ===== ТОП ПО SEOCOIN =====

@dp.message(F.text == "🍀 Топ по SeoCoin")
async def show_top_seocoin(message: Message):
    """Показывает ТОП по SeoCoin"""
    top_users = UserManager.get_top_seocoin(15)
    
    text = (
        "🍀 SeoCoin - валюта бота, которую Вы зарабатываете за выполнение "
        "заданий в боте! По итогам каждой недели ТОП 15 участников бота "
        "по сумме 🍀 SeoCoin вознаграждаются денежными призами!\n\n"
        "🍀 SeoCoin выдаются за выполнение заданий, приглашение рефералов, "
        "написание готовых отзывов, а также за размещение юзернейма бота "
        "в Вашем нике\n\n"
        "❗️За каждый день нахождения юзернейма бота - @jobseo_bot в Вашем "
        "нике в телеграм Вы будете получать по 5 🍀 SeoCoin\n\n"
        "❗️Для начисления бонусных 🍀 SeoCoin Вы должны хотя бы раз в сутки "
        "зайти и нажать кнопку в боте! Топ обновляется раз в сутки.\n\n"
        "🔝 ТОП участников по SeoCoin:\n"
    )
    
    medals = ["🥇", "🥈", "🥉"]
    for i, (username, coins) in enumerate(top_users, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        text += f"{medal} - {username} - {coins} 🍀\n"
    
    # Добавляем информацию о текущем пользователе
    user_id = message.from_user.id
    user = UserManager.get_user(user_id)
    user_seocoin = user.get("seocoin_weekly", 0)
    username = message.from_user.username or f"id{user_id}"
    if not username.startswith("@"):
        username = f"@{username}"
    
    text += f"\nВаш результат: {username} - {user_seocoin} 🍀"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="refresh_top")
    builder.button(text="« Назад", callback_data="back_to_main")
    
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "refresh_top")
async def refresh_top_callback(callback: CallbackQuery):
    """Обновляет ТОП"""
    await show_top_seocoin(callback.message)
    await callback.answer("Топ обновлен")

# ===== РЕФЕРАЛЬНАЯ ПРОГРАММА =====

@dp.message(F.text == "🧑‍🤝‍🧑 Реферальная программа")
async def show_referral(message: Message):
    """Показывает информацию о реферальной программе"""
    user_id = message.from_user.id
    user = UserManager.get_user(user_id)
    
    ref_link = f"https://t.me/{bot.username}?start=ref_{user_id}"
    
    text = (
        "🧑‍🤝‍🧑 РЕФЕРАЛЬНАЯ ПРОГРАММА\n\n"
        "❗️Реферал 1 уровня - это человек, который впервые заходит в бота "
        "по вашей ссылке. Когда человек зайдёт в бота по вашей ссылке, он "
        "навсегда становится вашим рефералом 1 уровня.\n"
        " - Когда ваш Реферал 1 уровня получает выплату за задание вы "
        "получаете 20% от его заработка на ваш баланс.\n\n"
        "❗️Реферал 2 уровня - это тот человек, который впервые заходит в "
        "бота по ссылке вашего Реферала 1 уровня.\n"
        " - Когда ваш Реферал 2 уровня получает выплату за задание вы "
        "получаете 5% от его заработка на ваш баланс.\n\n"
        "✅ Приглашайте новых пользователей и получайте пассивный доход "
        "от их заработка!\n\n"
        f"👁‍🗨 Ссылка для привлечения рефералов:\n{ref_link}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Поделиться", switch_inline_query=f"Зарабатывай со мной! {ref_link}")
    builder.button(text="📊 Мои рефералы", callback_data="my_referrals")
    
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "my_referrals")
async def my_referrals_callback(callback: CallbackQuery):
    """Показывает статистику рефералов"""
    user_id = callback.from_user.id
    user = UserManager.get_user(user_id)
    
    refs_1 = user.get("referrals_1", [])
    refs_2 = user.get("referrals_2", [])
    
    # Собираем информацию о рефералах
    refs_1_info = []
    for ref_id in refs_1[:10]:  # Показываем только первые 10
        ref_user = UserManager.get_user(int(ref_id))
        username = ref_user.get("username", f"id{ref_id}")
        earned = ref_user.get("total_earned", 0)
        refs_1_info.append(f"• {username} - заработал {earned:.2f} ₽")
    
    text = (
        f"📊 Статистика рефералов:\n\n"
        f"1 уровень: {len(refs_1)} чел.\n"
        f"2 уровень: {len(refs_2)} чел.\n"
        f"Заработано с рефералов: {user.get('referral_earnings', 0):.2f} ₽\n\n"
    )
    
    if refs_1_info:
        text += "Рефералы 1 уровня:\n" + "\n".join(refs_1_info)
    else:
        text += "У вас пока нет рефералов. Приглашайте друзей!"
    
    await callback.message.edit_text(text, reply_markup=get_back_button())
    await callback.answer()

# ===== ВЫВОД СРЕДСТВ =====

@dp.message(F.text == "💰 Вывод средств")
async def withdraw_start(message: Message, state: FSMContext):
    """Начало процесса вывода"""
    user_id = message.from_user.id
    user = UserManager.get_user(user_id)
    balance = user.get("balance", 0)
    
    if balance < 10:
        await message.answer(
            "❌ Минимальная сумма для вывода - 10 ₽\n"
            f"Ваш баланс: {balance:.2f} ₽\n\n"
            "Выполняйте задания, чтобы накопить нужную сумму!"
        )
        return
    
    await state.set_state(WithdrawalStates.choosing_system)
    await message.answer(
        f"💰 Вывод средств\n"
        f"Текущий баланс: {balance:.2f} ₽\n\n"
        "Выберите платежную систему:",
        reply_markup=get_withdrawal_systems_keyboard()
    )

@dp.callback_query(WithdrawalStates.choosing_system, F.data.startswith("withdraw_sys:"))
async def withdraw_system_chosen(callback: CallbackQuery, state: FSMContext):
    """Выбрана платежная система"""
    system = callback.data.split(":")[1]
    system_name = PAYMENT_SYSTEMS.get(system, system)
    
    await state.update_data(system=system, system_name=system_name)
    
    if system == "phone":
        await state.set_state(WithdrawalStates.entering_phone)
        text = (
            f"— Текущий баланс: {UserManager.get_user(callback.from_user.id)['balance']:.2f} ₽\n"
            f"— Платежная система: {system_name}\n\n"
            "❗️Внимание! Вывод по данной платежной системе возможен только на номер РФ.\n\n"
            "📱 Напишите номер телефона на который будет произведен вывод:"
        )
        await callback.message.edit_text(text, reply_markup=get_back_button())
    else:
        await state.set_state(WithdrawalStates.entering_account)
        
        if system in ["yoo", "crypto"]:
            extra = "\n\n⛔️ НЕ выводим на кошельки Украины." if system == "yoo" else ""
            text = (
                f"— Текущий баланс: {UserManager.get_user(callback.from_user.id)['balance']:.2f} ₽\n"
                f"— Платежная система: {system_name}\n\n"
                f"❗️ Внимание! Вывод по данной платежной системе возможен только на "
                f"{'верифицированные кошельки' if system == 'yoo' else 'криптокошельки'}.{extra}\n\n"
                f"💳 Напишите номер телефона или номер счета, привязанный к аккаунту:"
            )
        else:
            text = (
                f"— Текущий баланс: {UserManager.get_user(callback.from_user.id)['balance']:.2f} ₽\n"
                f"— Платежная система: {system_name}\n\n"
                f"💳 Напишите номер карты или счета:"
            )
        
        await callback.message.edit_text(text, reply_markup=get_back_button())
    
    await callback.answer()

@dp.message(WithdrawalStates.entering_phone)
async def withdraw_phone_entered(message: Message, state: FSMContext):
    """Введен номер телефона"""
    phone = message.text.strip()
    
    # Простейшая валидация
    if not phone.replace("+", "").replace("-", "").replace(" ", "").isdigit():
        await message.answer("❌ Неверный формат номера. Попробуйте снова:")
        return
    
    await state.update_data(account=phone)
    await state.set_state(WithdrawalStates.entering_amount)
    
    balance = UserManager.get_user(message.from_user.id)["balance"]
    await message.answer(
        f"💵 Введите сумму для вывода (мин. 10 ₽, макс. {balance:.2f} ₽):",
        reply_markup=get_cancel_keyboard()
    )

@dp.message(WithdrawalStates.entering_account)
async def withdraw_account_entered(message: Message, state: FSMContext):
    """Введен счет/кошелек"""
    account = message.text.strip()
    
    if len(account) < 5:
        await message.answer("❌ Слишком короткий номер. Попробуйте снова:")
        return
    
    await state.update_data(account=account)
    await state.set_state(WithdrawalStates.entering_amount)
    
    balance = UserManager.get_user(message.from_user.id)["balance"]
    await message.answer(
        f"💵 Введите сумму для вывода (мин. 10 ₽, макс. {balance:.2f} ₽):",
        reply_markup=get_cancel_keyboard()
    )

@dp.message(WithdrawalStates.entering_amount)
async def withdraw_amount_entered(message: Message, state: FSMContext):
    """Введена сумма вывода"""
    try:
        amount = float(message.text.strip().replace(",", "."))
    except:
        await message.answer("❌ Введите число (например: 100 или 50.5):")
        return
    
    user_id = message.from_user.id
    user = UserManager.get_user(user_id)
    balance = user.get("balance", 0)
    
    if amount < 10:
        await message.answer("❌ Минимальная сумма вывода - 10 ₽")
        return
    
    if amount > balance:
        await message.answer(f"❌ Недостаточно средств. Ваш баланс: {balance:.2f} ₽")
        return
    
    await state.update_data(amount=amount)
    data = await state.get_data()
    
    # Подтверждение
    text = (
        "📋 Проверьте данные:\n\n"
        f"Система: {data['system_name']}\n"
        f"Реквизиты: {data['account']}\n"
        f"Сумма: {amount:.2f} ₽\n\n"
        "Всё верно?"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="withdraw_confirm")
    builder.button(text="❌ Отмена", callback_data="withdraw_cancel")
    
    await message.answer(text, reply_markup=builder.as_markup())
    await state.set_state(WithdrawalStates.confirming)

@dp.callback_query(WithdrawalStates.confirming, F.data == "withdraw_confirm")
async def withdraw_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение вывода"""
    data = await state.get_data()
    user_id = callback.from_user.id
    
    # Создаем заявку
    req_id = WithdrawalManager.create_request(
        user_id=user_id,
        system=data["system"],
        account=data["account"],
        amount=data["amount"]
    )
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 Новая заявка на вывод!\n\n"
                f"От: @{callback.from_user.username or 'no_username'}\n"
                f"Сумма: {data['amount']:.2f} ₽\n"
                f"Система: {data['system_name']}\n"
                f"Реквизиты: {data['account']}\n"
                f"ID заявки: {req_id}"
            )
        except:
            pass
    
    await callback.message.edit_text(
        "✅ Заявка на вывод создана!\n\n"
        "Ожидайте подтверждения администратором. "
        "Обычно это занимает от нескольких минут до 24 часов."
    )
    
    await state.clear()
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(WithdrawalStates.confirming, F.data == "withdraw_cancel")
async def withdraw_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена вывода"""
    await state.clear()
    await callback.message.edit_text("❌ Вывод отменен")
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    await callback.answer()

# ===== ЗАДАНИЯ =====

@dp.message(F.text == "✍️ Приступить к заданию")
async def tasks_start(message: Message, state: FSMContext):
    """Начало работы с заданиями"""
    user_id = message.from_user.id
    user = UserManager.get_user(user_id)
    
    if not user.get("city"):
        await state.set_state(TaskStates.waiting_city)
        await message.answer(
            "🗺 Для выполнения заданий необходимо указать Вашу геолокацию. "
            "Напишите ваш город текстом или укажите геолокацию, нажав на кнопку в панели (только с телефона)\n\n"
            "❌ Если Вашего города нет в базе, то укажите ближайший крупный город\n"
            "❗️ Это необходимо для выдачи Вам заданий из Вашего города, что повышает шансы на прохождение отзыва!",
            reply_markup=get_location_keyboard()
        )
    else:
        await show_available_tasks(message, user["city"])

@dp.message(TaskStates.waiting_city, F.location)
async def process_location(message: Message, state: FSMContext):
    """Обработка геолокации"""
    # Здесь можно определить город по координатам
    # Для упрощения просим ввести город текстом
    await message.answer(
        "📍 Спасибо за геолокацию!\n"
        "Теперь напишите название вашего города текстом:"
    )

@dp.message(TaskStates.waiting_city, F.text)
async def process_city_text(message: Message, state: FSMContext):
    """Сохранение города из текста"""
    city = message.text.strip()
    
    # Сохраняем город
    UserManager.update_user(message.from_user.id, city=city)
    
    await message.answer(f"✅ Город {city} сохранен!", reply_markup=get_main_keyboard())
    await state.clear()
    
    # Показываем задания
    await show_available_tasks(message, city)

async def show_available_tasks(message: Message, city: str):
    """Показывает доступные задания"""
    user_id = message.from_user.id
    tasks = TaskManager.get_available_tasks(user_id, city)
    
    if not tasks:
        await message.answer(
            "😕 В вашем городе пока нет доступных заданий.\n"
            "Попробуйте зайти позже или изменить город в профиле."
        )
        return
    
    # Показываем первое задание
    await show_task(message, tasks[0])

async def show_task(message: Message, task: Dict):
    """Показывает одно задание"""
    text = (
        f"📝 Задание: {task['title']}\n\n"
        f"{task['description']}\n\n"
        f"💰 Награда: {task['reward']} ₽\n\n"
        f"📋 Инструкция:\n{task['instructions']}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Выполнил", callback_data=f"task_done:{task['id']}")
    builder.button(text="⏭ Следующее", callback_data="task_next")
    builder.button(text="❌ Отмена", callback_data="back_to_main")
    
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("task_done:"))
async def task_done_callback(callback: CallbackQuery, state: FSMContext):
    """Задание выполнено"""
    task_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    # Получаем задание
    tasks_data = JSONStorage._read(TASKS_FILE)
    task = tasks_data.get(task_id)
    
    if not task:
        await callback.answer("❌ Задание не найдено")
        return
    
    # Отмечаем как выполненное
    TaskManager.complete_task(user_id, task_id)
    
    # Начисляем награду и реферальные бонусы
    UserManager.process_task_completion(user_id, task["reward"])
    
    await callback.answer("✅ Задание принято! Награда начислена")
    
    # Показываем следующее задание
    tasks = TaskManager.get_available_tasks(user_id, UserManager.get_user(user_id).get("city"))
    if tasks:
        await show_task(callback.message, tasks[0])
    else:
        await callback.message.edit_text(
            "🎉 Поздравляем! Вы выполнили все доступные задания!\n"
            "Заходите позже, появятся новые."
        )

@dp.callback_query(F.data == "task_next")
async def task_next_callback(callback: CallbackQuery):
    """Следующее задание"""
    user_id = callback.from_user.id
    user = UserManager.get_user(user_id)
    tasks = TaskManager.get_available_tasks(user_id, user.get("city"))
    
    if tasks:
        await show_task(callback.message, tasks[0])
    else:
        await callback.message.edit_text("😕 Больше заданий нет")

@dp.message(F.text == "📦 Доп. задания")
async def extra_tasks(message: Message):
    """Дополнительные задания"""
    text = (
        "⚡️ Для дополнительных заданий для Вас создан отдельный чат "
        f"{EXTRA_TASKS_CHAT} с ГОТОВЫМИ отзывами\n\n"
        "✍🏻 В данном чате Вам выдают готовые тексты для публикации, вместо инструкции\n\n"
        "✅ Никакого общения, только задания! Ничего не будет отвлекать Вас от заработка"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Перейти в чат", url=EXTRA_TASKS_CHAT)
    
    await message.answer(text, reply_markup=builder.as_markup())

# ===== ПОМОЩЬ =====

@dp.message(F.text == "🛡 Помощь")
async def help_section(message: Message):
    """Раздел помощи"""
    text = (
        "📲 В данном разделе указаны контакты поддержки для оперативного решения "
        "Ваших вопросов, а также ссылки на основные наши ресурсы\n\n"
        "⏰ Поддержка работает для Вас 24/7 без праздников и выходных\n"
        "🤝 Наша поддержка всегда поможет Вам с любыми проблемами по работе бота!"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❓ FAQ", url=FAQ_LINK)
    builder.button(text="📢 Канал", url=CHANNEL_LINK)
    builder.button(text="📑 Отзывы", url=REVIEWS_LINK)
    builder.button(text="🛠 Поддержка", url=SUPPORT_LINK)
    builder.button(text="💬 Чат", url=CHAT_LINK)
    builder.adjust(2)
    
    await message.answer(text, reply_markup=builder.as_markup())

# ===== АДМИН-ПАНЕЛЬ =====

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    """Вход в админ-панель"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Доступ запрещен")
        return
    
    await message.answer(
        "👑 Админ-панель\n\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )

@dp.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(callback: CallbackQuery, state: FSMContext):
    """Обработка админских callback"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Доступ запрещен")
        return
    
    action = callback.data.replace("admin_", "")
    
    if action == "mailing":
        await state.set_state(AdminStates.mailing_message)
        await callback.message.edit_text(
            "📨 Введите сообщение для рассылки (можно использовать HTML-разметку):",
            reply_markup=get_back_button()
        )
    
    elif action == "stats":
        users = UserManager.get_all_users()
        tasks = JSONStorage._read(TASKS_FILE)
        withdrawals = JSONStorage._read(WITHDRAWALS_FILE)
        
        total_balance = sum(u.get("balance", 0) for u in users.values())
        total_seocoin = sum(u.get("seocoin", 0) for u in users.values())
        active_users = sum(1 for u in users.values() 
                          if datetime.fromisoformat(u.get("last_activity", "2000-01-01")) > datetime.now() - timedelta(days=7))
        
        stats_text = (
            "📊 СТАТИСТИКА БОТА\n\n"
            f"👥 Всего пользователей: {len(users)}\n"
            f"✅ Активных за неделю: {active_users}\n"
            f"💰 Общий баланс: {total_balance:.2f} ₽\n"
            f"🍀 Всего SeoCoin: {total_seocoin}\n"
            f"📝 Заданий: {len(tasks)}\n"
            f"💸 Заявок на вывод: {len(withdrawals)}\n"
            f"⏳ Ожидают обработки: {len(WithdrawalManager.get_pending_requests())}"
        )
        
        await callback.message.edit_text(stats_text, reply_markup=get_admin_keyboard())
    
    elif action == "add_seocoin":
        await state.set_state(AdminStates.add_seocoin_user)
        await callback.message.edit_text(
            "➕ Введите ID пользователя для начисления SeoCoin:",
            reply_markup=get_back_button()
        )
    
    elif action == "remove_seocoin":
        await state.set_state(AdminStates.remove_seocoin_user)
        await callback.message.edit_text(
            "➖ Введите ID пользователя для списания SeoCoin:",
            reply_markup=get_back_button()
        )
    
    elif action == "withdrawals":
        pending = WithdrawalManager.get_pending_requests()
        
        if not pending:
            await callback.message.edit_text(
                "💰 Нет ожидающих заявок на вывод",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer()
            return
        
        text = "💰 Ожидающие заявки на вывод:\n\n"
        builder = InlineKeyboardBuilder()
        
        for req_id, req in pending.items():
            user = UserManager.get_user(req["user_id"])
            username = user.get("username", f"id{req['user_id']}")
            text += f"ID {req_id}: @{username} - {req['amount']:.2f} ₽ ({req['system']})\n"
            builder.button(text=f"✅ {req_id}", callback_data=f"approve_withdraw:{req_id}")
            builder.button(text=f"❌ {req_id}", callback_data=f"reject_withdraw:{req_id}")
        
        builder.adjust(2)
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    
    elif action == "find_user":
        await state.set_state(AdminStates.find_user_id)
        await callback.message.edit_text(
            "🔍 Введите ID или username пользователя:",
            reply_markup=get_back_button()
        )
    
    elif action == "create_task":
        await state.set_state(AdminStates.create_task_title)
        await callback.message.edit_text(
            "📝 Введите название задания:",
            reply_markup=get_back_button()
        )
    
    await callback.answer()

@dp.message(AdminStates.mailing_message)
async def admin_mailing(message: Message, state: FSMContext):
    """Отправка рассылки"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    text = message.html_text
    users = UserManager.get_all_users()
    
    sent = 0
    failed = 0
    
    status_msg = await message.answer("📨 Начинаю рассылку...")
    
    for user_id in users:
        try:
            await bot.send_message(int(user_id), text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # Чтобы не флудить
        except:
            failed += 1
        
        if (sent + failed) % 10 == 0:
            await status_msg.edit_text(f"📨 Прогресс: отправлено {sent}, ошибок {failed}")
    
    await status_msg.edit_text(f"✅ Рассылка завершена!\nОтправлено: {sent}\nОшибок: {failed}")
    await state.clear()

@dp.message(AdminStates.add_seocoin_user)
async def admin_add_seocoin_user(message: Message, state: FSMContext):
    """Ввод пользователя для начисления SeoCoin"""
    try:
        user_id = int(message.text.strip())
        UserManager.get_user(user_id)  # Проверяем существование
        await state.update_data(target_user=user_id)
        await state.set_state(AdminStates.add_seocoin_amount)
        await message.answer("💰 Введите количество SeoCoin для начисления:")
    except:
        await message.answer("❌ Неверный ID. Попробуйте снова:")

@dp.message(AdminStates.add_seocoin_amount)
async def admin_add_seocoin_amount(message: Message, state: FSMContext):
    """Начисление SeoCoin"""
    try:
        amount = int(message.text.strip())
        data = await state.get_data()
        user_id = data["target_user"]
        
        if UserManager.add_seocoin(user_id, amount):
            await message.answer(f"✅ Начислено {amount} SeoCoin пользователю {user_id}")
        else:
            await message.answer("❌ Ошибка начисления")
        
        await state.clear()
    except:
        await message.answer("❌ Введите число:")

@dp.message(AdminStates.remove_seocoin_user)
async def admin_remove_seocoin_user(message: Message, state: FSMContext):
    """Ввод пользователя для списания SeoCoin"""
    try:
        user_id = int(message.text.strip())
        await state.update_data(target_user=user_id)
        await state.set_state(AdminStates.remove_seocoin_amount)
        await message.answer("💰 Введите количество SeoCoin для списания:")
    except:
        await message.answer("❌ Неверный ID. Попробуйте снова:")

@dp.message(AdminStates.remove_seocoin_amount)
async def admin_remove_seocoin_amount(message: Message, state: FSMContext):
    """Списание SeoCoin"""
    try:
        amount = int(message.text.strip())
        data = await state.get_data()
        user_id = data["target_user"]
        
        if UserManager.remove_seocoin(user_id, amount):
            await message.answer(f"✅ Списано {amount} SeoCoin у пользователя {user_id}")
        else:
            await message.answer("❌ Недостаточно SeoCoin или ошибка списания")
        
        await state.clear()
    except:
        await message.answer("❌ Введите число:")

@dp.callback_query(F.data.startswith("approve_withdraw:"))
async def approve_withdraw(callback: CallbackQuery):
    """Одобрение вывода"""
    req_id = callback.data.split(":")[1]
    
    if WithdrawalManager.process_request(req_id, callback.from_user.id, approve=True):
        # Уведомляем пользователя
        req_data = JSONStorage._read(WITHDRAWALS_FILE)[req_id]
        try:
            await bot.send_message(
                req_data["user_id"],
                f"✅ Ваша заявка на вывод {req_data['amount']:.2f} ₽ одобрена!\n"
                f"Средства будут отправлены в ближайшее время."
            )
        except:
            pass
        
        await callback.answer("✅ Заявка одобрена")
    else:
        await callback.answer("❌ Ошибка")
    
    # Обновляем список заявок
    await admin_callbacks(callback, None)

@dp.callback_query(F.data.startswith("reject_withdraw:"))
async def reject_withdraw(callback: CallbackQuery):
    """Отклонение вывода"""
    req_id = callback.data.split(":")[1]
    
    if WithdrawalManager.process_request(req_id, callback.from_user.id, approve=False):
        # Уведомляем пользователя
        req_data = JSONStorage._read(WITHDRAWALS_FILE)[req_id]
        try:
            await bot.send_message(
                req_data["user_id"],
                f"❌ Ваша заявка на вывод {req_data['amount']:.2f} ₽ отклонена.\n"
                f"Свяжитесь с поддержкой для уточнения причин."
            )
        except:
            pass
        
        await callback.answer("❌ Заявка отклонена")
    else:
        await callback.answer("❌ Ошибка")
    
    # Обновляем список заявок
    await admin_callbacks(callback, None)

@dp.message(AdminStates.find_user_id)
async def admin_find_user(message: Message, state: FSMContext):
    """Поиск пользователя"""
    query = message.text.strip().lower()
    users = UserManager.get_all_users()
    
    found = []
    for uid, uinfo in users.items():
        if query in uid or (uinfo.get("username") and query in uinfo.get("username").lower()):
            found.append((uid, uinfo))
    
    if not found:
        await message.answer("❌ Пользователь не найден")
        await state.clear()
        return
    
    text = "🔍 Найденные пользователи:\n\n"
    builder = InlineKeyboardBuilder()
    
    for uid, uinfo in found[:10]:  # Показываем первые 10
        username = uinfo.get("username", f"id{uid}")
        balance = uinfo.get("balance", 0)
        seocoin = uinfo.get("seocoin", 0)
        text += f"ID: {uid}\n@{username}\n💰 {balance:.2f} ₽ | 🍀 {seocoin}\n\n"
        builder.button(text=f"📊 {username}", callback_data=f"user_stats:{uid}")
    
    builder.adjust(2)
    await message.answer(text, reply_markup=builder.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("user_stats:"))
async def user_stats_callback(callback: CallbackQuery):
    """Статистика конкретного пользователя"""
    user_id = int(callback.data.split(":")[1])
    user = UserManager.get_user(user_id)
    
    text = (
        f"📊 Статистика пользователя {user_id}\n\n"
        f"Username: @{user.get('username', 'нет')}\n"
        f"Статус: {user.get('status')}\n"
        f"Баланс: {user.get('balance', 0):.2f} ₽\n"
        f"SeoCoin: {user.get('seocoin', 0)}\n"
        f"Всего заработано: {user.get('total_earned', 0):.2f} ₽\n"
        f"Заданий выполнено: {user.get('tasks_completed', 0)}\n"
        f"Рефералов 1 ур.: {len(user.get('referrals_1', []))}\n"
        f"Рефералов 2 ур.: {len(user.get('referrals_2', []))}\n"
        f"Заработано с рефералов: {user.get('referral_earnings', 0):.2f} ₽\n"
        f"Город: {user.get('city', 'не указан')}\n"
        f"Регистрация: {user.get('registered_at', 'неизвестно')[:10]}"
    )
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.message(AdminStates.create_task_title)
async def admin_create_task_title(message: Message, state: FSMContext):
    """Создание задания - название"""
    await state.update_data(title=message.text)
    await state.set_state(AdminStates.create_task_desc)
    await message.answer("📝 Введите описание задания:")

@dp.message(AdminStates.create_task_desc)
async def admin_create_task_desc(message: Message, state: FSMContext):
    """Создание задания - описание"""
    await state.update_data(description=message.text)
    await state.set_state(AdminStates.create_task_reward)
    await message.answer("💰 Введите награду за задание (в рублях):")

@dp.message(AdminStates.create_task_reward)
async def admin_create_task_reward(message: Message, state: FSMContext):
    """Создание задания - награда"""
    try:
        reward = float(message.text.strip())
        await state.update_data(reward=reward)
        await state.set_state(AdminStates.create_task_city)
        await message.answer(
            "🌆 Введите город для задания (или '-' если для всех городов):"
        )
    except:
        await message.answer("❌ Введите число:")

@dp.message(AdminStates.create_task_city)
async def admin_create_task_city(message: Message, state: FSMContext):
    """Создание задания - город"""
    city = message.text.strip()
    if city == "-":
        city = None
    
    await state.update_data(city=city)
    await state.set_state(AdminStates.create_task_instructions)
    await message.answer("📋 Введите инструкцию для выполнения задания:")

@dp.message(AdminStates.create_task_instructions)
async def admin_create_task_instructions(message: Message, state: FSMContext):
    """Создание задания - инструкция"""
    data = await state.get_data()
    data["instructions"] = message.text
    data["created_by"] = message.from_user.id
    
    task_id = TaskManager.create_task(data)
    
    await message.answer(f"✅ Задание создано!\nID задания: {task_id}")
    await state.clear()

# ===== ОБЩИЕ КНОПКИ =====

@dp.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer("Действие отменено", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    await callback.answer()

# ===== ФОНОВЫЕ ЗАДАЧИ =====

async def check_usernames_daily():
    """Ежедневная проверка наличия юзернейма бота в нике"""
    while True:
        logger.info("Checking usernames for SeoCoin bonus...")
        
        users = UserManager.get_all_users()
        bot_username = (await bot.get_me()).username
        
        for uid, uinfo in users.items():
            # Проверяем, был ли уже бонус сегодня
            last_check = uinfo.get("last_username_check")
            if last_check:
                last = datetime.fromisoformat(last_check)
                if last.date() == datetime.now().date():
                    continue
            
            # В реальном проекте тут проверка через Telegram API
            # Для демо используем рандом
            if UserManager.check_username_in_nickname(int(uid), bot_username):
                UserManager.add_seocoin(int(uid), SEOCOIN_PER_DAY_USERNAME)
                UserManager.update_user(int(uid), last_username_check=datetime.now().isoformat())
            
            await asyncio.sleep(0.1)
        
        # Ждем до следующего дня
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        sleep_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

async def reset_weekly_top():
    """Сброс недельного топа"""
    while True:
        now = datetime.now()
        # Сброс каждый понедельник в 00:00
        next_monday = (now + timedelta(days=(7 - now.weekday()) % 7 or 7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sleep_seconds = (next_monday - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        
        logger.info("Resetting weekly SeoCoin top...")
        UserManager.reset_weekly_seocoin()

# ===== ЗАПУСК =====

async def main():
    """Точка входа"""
    # Проверка токена
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ОШИБКА: Вставьте свой токен бота в переменную BOT_TOKEN!")
        return
    
    # Удаляем вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_usernames_daily())
    asyncio.create_task(reset_weekly_top())
    
    logger.info("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())