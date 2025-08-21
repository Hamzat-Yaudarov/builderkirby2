#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import aiohttp
import asyncpg
import random
import os
from datetime import datetime, timedelta, date
from typing import Optional
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================================
# НАСТРОЙКИ
# ================================
BOT_TOKEN = "8379368723:AAEnG133OZ4qMrb5vQfM7VdEFSuLiWydsyM"
SUBGRAM_API_KEY = "5d4c6c5283559a05a9558b677669871d6ab58e00e71587546b25b4940ea6029d"
DATABASE_URL = "postgresql://neondb_owner:npg_s6iWtmzZU8XA@ep-dawn-waterfall-a23jn5vi-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
ADMIN_CHAT_ID = "@kirbyvivodstars"
PAYMENTS_CHAT_ID = "@kirbystarspayments"
ADMIN_IDS = [5678901234]  # ЗАМЕНИТЕ НА ВАШИ ID!

# ================================
# ИНИЦИАЛИЗАЦИЯ
# ================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db_pool: Optional[asyncpg.Pool] = None

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Проверим токен при запуске
logger.info(f"🔑 Используется токен: {BOT_TOKEN[:10]}...")

# ================================
# СОСТОЯНИЯ FSM
# ================================
class UserStates(StatesGroup):
    waiting_for_promo_code = State()

class AdminStates(StatesGroup):
    waiting_for_task_name = State()
    waiting_for_task_url = State()
    waiting_for_task_reward = State()
    waiting_for_promo_code = State()
    waiting_for_promo_reward = State()
    waiting_for_promo_uses = State()
    waiting_for_rejection_reason = State()

# ================================
# БАЗА ДАННЫХ
# ================================
async def init_db():
    """Инициализация базы данных"""
    global db_pool
    try:
        logger.info("🔄 Подключение к базе данных...")
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        logger.info("✅ Подключение к базе данных установлено")
        
        async with db_pool.acquire() as conn:
            logger.info("🔄 Создание таблиц...")
            
            # Основная таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(100),
                    first_name VARCHAR(100),
                    balance DECIMAL(10, 2) DEFAULT 0,
                    referral_earnings DECIMAL(10, 2) DEFAULT 0,
                    total_earnings DECIMAL(10, 2) DEFAULT 0,
                    points INTEGER DEFAULT 0,
                    weekly_points INTEGER DEFAULT 0,
                    clicks_today INTEGER DEFAULT 0,
                    last_click_reset DATE DEFAULT CURRENT_DATE,
                    next_click_time TIMESTAMP DEFAULT NOW(),
                    daily_case_opened BOOLEAN DEFAULT FALSE,
                    last_case_reset DATE DEFAULT CURRENT_DATE,
                    referrer_id BIGINT,
                    registration_date TIMESTAMP DEFAULT NOW(),
                    subscription_checked BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Остальные таблицы
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT,
                    referred_id BIGINT,
                    date_referred TIMESTAMP DEFAULT NOW(),
                    tasks_completed INTEGER DEFAULT 0,
                    reward_given BOOLEAN DEFAULT FALSE
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200),
                    url VARCHAR(500),
                    reward DECIMAL(10, 2),
                    is_subgram BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    task_id INTEGER,
                    completed BOOLEAN DEFAULT FALSE,
                    completed_at TIMESTAMP,
                    UNIQUE(user_id, task_id)
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    amount DECIMAL(10, 2),
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    processed_at TIMESTAMP,
                    rejection_reason TEXT
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) UNIQUE,
                    reward DECIMAL(10, 2),
                    max_uses INTEGER,
                    current_uses INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS promo_uses (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    promo_id INTEGER,
                    used_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, promo_id)
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS lotteries (
                    id SERIAL PRIMARY KEY,
                    ticket_count INTEGER,
                    ticket_price DECIMAL(10, 2),
                    bot_percent INTEGER,
                    winner_count INTEGER,
                    tickets_sold INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    ended BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    ended_at TIMESTAMP
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS lottery_tickets (
                    id SERIAL PRIMARY KEY,
                    lottery_id INTEGER,
                    user_id BIGINT,
                    ticket_number INTEGER,
                    purchased_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
        logger.info("✅ Все таблицы созданы успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise

async def get_db_connection():
    """Получить подключение к БД"""
    if db_pool is None:
        await init_db()
    return db_pool.acquire()

# ================================
# SUBGRAM API
# ================================
async def check_subscription(user_id: int, chat_id: int, first_name: str = "", language_code: str = "ru", is_premium: bool = False):
    """Проверка подписки через SubGram"""
    url = "https://api.subgram.ru/request-op/"
    headers = {"Auth": SUBGRAM_API_KEY, "Content-Type": "application/json"}
    
    data = {
        "UserId": str(user_id),
        "ChatId": str(chat_id),
        "first_name": first_name,
        "language_code": language_code,
        "Premium": is_premium,
        "action": "subscribe"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                result = await response.json()
                logger.info(f"SubGram ответ: {result.get('status', 'unknown')}")
                return result
    except Exception as e:
        logger.error(f"Ошибка SubGram API: {e}")
        return {"status": "error", "message": "Ошибка API"}

async def get_subgram_tasks(user_id: int, chat_id: int):
    """Получить задания от SubGram"""
    url = "https://api.subgram.ru/request-op/"
    headers = {"Auth": SUBGRAM_API_KEY, "Content-Type": "application/json"}
    
    data = {
        "UserId": str(user_id),
        "ChatId": str(chat_id),
        "action": "newtask",
        "MaxOP": 1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                result = await response.json()
                return result
    except Exception as e:
        logger.error(f"Ошибка SubGram tasks API: {e}")
        return {"status": "error", "message": "Ошибка API"}

# ================================
# КЛАВИАТУРЫ
# ================================
def create_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referrals")],
        [InlineKeyboardButton(text="🖱 Кликер", callback_data="clicker")],
        [InlineKeyboardButton(text="💫 Вывод звёзд", callback_data="withdrawal")],
        [InlineKeyboardButton(text="📋 Задания", callback_data="tasks")],
        [InlineKeyboardButton(text="📚 Инструкция", callback_data="instructions")],
        [InlineKeyboardButton(text="🏆 Рейтинги", callback_data="ratings")],
        [InlineKeyboardButton(text="📦 Кейсы", callback_data="cases")],
        [InlineKeyboardButton(text="🎲 Лотерея", callback_data="lottery")]
    ])

def create_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
    ])

def create_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Промокод", callback_data="promo_code")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
    ])

# ================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ================================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None, referrer_id: int = None):
    try:
        async with get_db_connection() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                logger.info(f"Создание нового пользователя {user_id}")
                await conn.execute('''
                    INSERT INTO users (user_id, username, first_name, referrer_id)
                    VALUES ($1, $2, $3, $4)
                ''', user_id, username, first_name, referrer_id)
                
                if referrer_id:
                    await conn.execute('''
                        INSERT INTO referrals (referrer_id, referred_id)
                        VALUES ($1, $2)
                    ''', referrer_id, user_id)
                
                user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            return user
    except Exception as e:
        logger.error(f"Ошибка создания пользователя: {e}")
        return None

async def update_daily_counters(user_id: int):
    try:
        async with get_db_connection() as conn:
            today = date.today()
            await conn.execute('''
                UPDATE users 
                SET clicks_today = CASE WHEN last_click_reset < $1 THEN 0 ELSE clicks_today END,
                    last_click_reset = CASE WHEN last_click_reset < $1 THEN $1 ELSE last_click_reset END,
                    next_click_time = CASE WHEN last_click_reset < $1 THEN NOW() ELSE next_click_time END,
                    daily_case_opened = CASE WHEN last_case_reset < $1 THEN FALSE ELSE daily_case_opened END,
                    last_case_reset = CASE WHEN last_case_reset < $1 THEN $1 ELSE last_case_reset END
                WHERE user_id = $2
            ''', today, user_id)
    except Exception as e:
        logger.error(f"Ошибка обновления счетчиков: {e}")

# ================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# ================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    logger.info(f"📨 /start от пользователя {message.from_user.id} (@{message.from_user.username})")
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    try:
        # Извлечь реферера
        referrer_id = None
        if message.text and len(message.text.split()) > 1:
            try:
                referrer_id = int(message.text.split()[1])
                if referrer_id == user_id:
                    referrer_id = None
                logger.info(f"Реферер: {referrer_id}")
            except:
                pass
        
        # Создать пользователя
        user = await get_or_create_user(user_id, username, first_name, referrer_id)
        if not user:
            await message.answer("❌ Ошибка базы данных. Попробуйте позже.")
            return
            
        await update_daily_counters(user_id)
        
        # Проверить подписку
        logger.info(f"Проверка подписки для {user_id}")
        sub_result = await check_subscription(
            user_id, message.chat.id, first_name or "", 
            message.from_user.language_code or "ru", 
            message.from_user.is_premium or False
        )
        
        if sub_result.get("status") == "ok":
            logger.info(f"Пользователь {user_id} подписан")
            async with get_db_connection() as conn:
                await conn.execute("UPDATE users SET subscription_checked = TRUE WHERE user_id = $1", user_id)
            
            keyboard = create_main_menu_keyboard()
            await message.answer(
                "🌟 <b>Добро пожаловать в бота для заработка звёзд!</b>\n\n"
                "Выберите действие из меню ниже:",
                reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            logger.info(f"Пользователь {user_id} не подписан")
            if sub_result.get("links"):
                links_text = "\n".join([f"• {link}" for link in sub_result["links"]])
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="subgram-op")]
                ])
                await message.answer(
                    "🔔 <b>Для использования бота необходимо подписаться на спонсорские каналы:</b>\n\n"
                    f"{links_text}\n\nПосле подписки нажмите кнопку ниже:",
                    reply_markup=keyboard, parse_mode="HTML"
                )
            else:
                await message.answer("❌ Ошибка получения спонсорских каналов. Попробуйте позже.")
    
    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    logger.info(f"📨 /admin от пользователя {message.from_user.id}")
    
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    await message.answer("👑 <b>Админ-панель</b>\n\n🚧 В разработке", parse_mode="HTML")

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая команда для проверки работы бота"""
    logger.info(f"📨 /test от пользователя {message.from_user.id}")
    await message.answer("✅ Бот работает! Используйте /start для начала.")

# ================================
# CALLBACK ОБРАБОТЧИКИ
# ================================
@dp.callback_query(F.data.startswith("subgram"))
async def callback_subgram(callback: types.CallbackQuery):
    logger.info(f"🔄 SubGram callback от {callback.from_user.id}")
    user_id = callback.from_user.id
    
    if callback.data == "subgram-op":
        sub_result = await check_subscription(
            user_id, callback.message.chat.id,
            callback.from_user.first_name or "",
            callback.from_user.language_code or "ru",
            callback.from_user.is_premium or False
        )
        
        if sub_result.get("status") == "ok":
            async with get_db_connection() as conn:
                await conn.execute("UPDATE users SET subscription_checked = TRUE WHERE user_id = $1", user_id)
            
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "🌟 <b>Добро пожаловать в бота для заработка звёзд!</b>\n\nВыберите действие из меню ниже:",
                reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            if sub_result.get("links"):
                links_text = "\n".join([f"• {link}" for link in sub_result["links"]])
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="subgram-op")]
                ])
                await callback.message.edit_text(
                    "⚠️ <b>Вы ещё не подписались на все каналы!</b>\n\n"
                    f"{links_text}\n\nПосле подписки нажмите кнопку ниже:",
                    reply_markup=keyboard, parse_mode="HTML"
                )
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: types.CallbackQuery):
    logger.info(f"🏠 Главное меню от {callback.from_user.id}")
    keyboard = create_main_menu_keyboard()
    await callback.message.edit_text("🌟 <b>Главное меню</b>\n\nВыберите действие:",
                                     reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def callback_profile(callback: types.CallbackQuery):
    logger.info(f"👤 Профиль от {callback.from_user.id}")
    user_id = callback.from_user.id
    
    try:
        async with get_db_connection() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            referral_count = await conn.fetchval(
                "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1", user_id
            ) or 0
            
            daily_refs = await conn.fetchval(
                "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1 AND DATE(date_referred) = CURRENT_DATE", user_id
            ) or 0
        
        keyboard = create_profile_keyboard()
        profile_text = f"""👤 <b>Ваш профиль</b>

🆔 <b>ID:</b> {user['user_id']}
👤 <b>Юзернейм:</b> @{user['username'] or 'Не указан'}
💫 <b>Баланс:</b> {user['balance']} звёзд
💰 <b>Заработано с рефералов:</b> {user['referral_earnings']} звёзд
💎 <b>Всего заработано:</b> {user['total_earnings']} звёзд
👥 <b>Всего рефералов:</b> {referral_count}
📅 <b>Рефералов за день:</b> {daily_refs}
🏆 <b>Очки:</b> {user['points']}"""

        await callback.message.edit_text(profile_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в профиле: {e}")
        await callback.answer("❌ Ошибка загрузки профиля", show_alert=True)
    
    await callback.answer()

# Заглушки для остальных функций
@dp.callback_query(F.data.in_(["referrals", "clicker", "withdrawal", "tasks", "ratings", "cases", "lottery", "instructions", "promo_code"]))
async def callback_placeholder(callback: types.CallbackQuery):
    logger.info(f"🚧 {callback.data} от {callback.from_user.id}")
    await callback.answer("🚧 Функция в разработке. Скоро будет готова!", show_alert=True)

# ================================
# ЗАПУСК БОТА
# ================================
async def main():
    try:
        logger.info("🚀 Запуск бота...")
        
        # Инициализируем базу данных
        await init_db()
        
        # Проверяем токен бота
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот запущен: @{bot_info.username} ({bot_info.first_name})")
        
        # Запускаем polling
        logger.info("🔄 Начинаем polling...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db_pool:
            logger.info("🔄 Закрытие подключения к БД...")
            await db_pool.close()
        logger.info("👋 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())
