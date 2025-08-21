#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import aiohttp
import asyncpg
import random
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
ADMIN_IDS = [7972065986]  # ЗАМЕНИТЕ НА ВАШИ ID!

# ================================
# ИНИЦИАЛИЗАЦИЯ
# ================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db_pool: Optional[asyncpg.Pool] = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        logger.info("✅ Подключение к базе данных установлено")
        
        async with db_pool.acquire() as conn:
            # Создание таблиц
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
            
        logger.info("✅ База данных инициализирована")
        
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
                return result
    except Exception as e:
        logger.error(f"Ошибка SubGram API: {e}")
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

def create_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📋 Задани��", callback_data="admin_tasks")],
        [InlineKeyboardButton(text="🎫 Промокоды", callback_data="admin_promos")],
        [InlineKeyboardButton(text="💫 Выводы", callback_data="admin_withdrawals")]
    ])

# ================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ================================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None, referrer_id: int = None):
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not user:
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

async def update_daily_counters(user_id: int):
    async with get_db_connection() as conn:
        today = date.today()
        await conn.execute('''
            UPDATE users 
            SET clicks_today = 0, last_click_reset = $1, next_click_time = NOW(),
                daily_case_opened = FALSE, last_case_reset = $1
            WHERE user_id = $2 AND (last_click_reset < $1 OR last_case_reset < $1)
        ''', today, user_id)

# ================================
# ОБРАБОТЧИКИ КОМАНД
# ================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Извлечь реферера
    referrer_id = None
    if message.text and len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    # Создать пользователя
    await get_or_create_user(user_id, username, first_name, referrer_id)
    await update_daily_counters(user_id)
    
    # Проверить подписку
    sub_result = await check_subscription(
        user_id, message.chat.id, first_name or "", 
        message.from_user.language_code or "ru", 
        message.from_user.is_premium or False
    )
    
    if sub_result.get("status") == "ok":
        async with get_db_connection() as conn:
            await conn.execute("UPDATE users SET subscription_checked = TRUE WHERE user_id = $1", user_id)
        
        keyboard = create_main_menu_keyboard()
        await message.answer(
            "🌟 <b>Добро пожаловать в бота для заработка звёзд!</b>\n\n"
            "Выберите действие из меню ниже:",
            reply_markup=keyboard, parse_mode="HTML"
        )
    else:
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

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    keyboard = create_admin_keyboard()
    await message.answer("👑 <b>Админ-панель</b>\n\nВыберите действие:", 
                         reply_markup=keyboard, parse_mode="HTML")

# ================================
# ОБРАБОТЧИКИ CALLBACK
# ================================
@dp.callback_query(F.data.startswith("subgram"))
async def callback_subgram(callback: types.CallbackQuery):
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
    keyboard = create_main_menu_keyboard()
    await callback.message.edit_text("🌟 <b>Главное меню</b>\n\nВыберите действие:",
                                     reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def callback_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        referral_count = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1", user_id
        ) or 0
    
    keyboard = create_profile_keyboard()
    profile_text = f"""👤 <b>Ваш профиль</b>

🆔 <b>ID:</b> {user['user_id']}
👤 <b>Юзернейм:</b> @{user['username'] or 'Не указан'}
💫 <b>Баланс:</b> {user['balance']} звёзд
💰 <b>Заработано с рефералов:</b> {user['referral_earnings']} звёзд
💎 <b>Всего заработано:</b> {user['total_earnings']} звёзд
👥 <b>Всего рефералов:</b> {referral_count}
��� <b>Очки:</b> {user['points']}"""

    await callback.message.edit_text(profile_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "referrals")
async def callback_referrals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/kirbystarsfarmbot?start={user_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referrals"),
         InlineKeyboardButton(text="📋 Задания", callback_data="tasks")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
    ])
    
    text = f"""👥 <b>Реферальная система</b>

💡 <b>Как это работает:</b>
• Приглашайте друзей по вашей ссылке
• Друг должен подписаться на все спонсорские каналы
• Друг должен выполнить 2 задания
• За каждого реферала вы получаете <b>2 звезды</b>

🔗 <b>Ваша реферальная ссылка:</b>
<code>{ref_link}</code>"""

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "clicker")
async def callback_clicker(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        now = datetime.now()
        clicks_today = user['clicks_today']
        next_click_time = user['next_click_time']
        
        if clicks_today >= 10:
            keyboard = create_back_keyboard()
            await callback.message.edit_text(
                "🖱 <b>Кликер</b>\n\n❌ Вы уже использовали все 10 кликов на сегодня!\nПриходите завтра.",
                reply_markup=keyboard, parse_mode="HTML"
            )
        elif now < next_click_time:
            time_left = next_click_time - now
            minutes = int(time_left.total_seconds() / 60)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🖱 Кликнуть", callback_data="click")],
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(
                f"🖱 <b>Кликер</b>\n\n⏰ До следующего клика: {minutes} мин\n"
                f"🖱 Кликов сегодня: {clicks_today}/10\n💫 За клик: 0.1 звезды",
                reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🖱 Кликнуть", callback_data="click")],
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(
                f"🖱 <b>Кликер</b>\n\n✅ Вы можете кликнуть!\n"
                f"🖱 Кликов сегодня: {clicks_today}/10\n💫 За клик: 0.1 звезды",
                reply_markup=keyboard, parse_mode="HTML"
            )
    
    await callback.answer()

@dp.callback_query(F.data == "click")
async def callback_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not user:
            await callback.answer("❌ Ошибка", show_alert=True)
            return
        
        now = datetime.now()
        clicks_today = user['clicks_today']
        
        if clicks_today >= 10:
            await callback.answer("❌ Лимит кликов исчерпан!", show_alert=True)
            return
        
        if now < user['next_click_time']:
            await callback.answer("⏰ Ещё рано для клика!", show_alert=True)
            return
        
        # Обработать клик
        new_clicks = clicks_today + 1
        reward = 0.1
        wait_minutes = new_clicks * 5
        new_next_click = now + timedelta(minutes=wait_minutes)
        
        await conn.execute('''
            UPDATE users 
            SET balance = balance + $1, total_earnings = total_earnings + $1,
                clicks_today = $2, next_click_time = $3, points = points + 1,
                weekly_points = weekly_points + 1
            WHERE user_id = $4
        ''', reward, new_clicks, new_next_click, user_id)
        
        new_balance = float(user['balance']) + reward
        
        if new_clicks >= 10:
            keyboard = create_back_keyboard()
            text = f"🖱 <b>Кликер</b>\n\n✅ Клик засчитан! +{reward} звезды\n" \
                   f"💫 Баланс: {new_balance} звёзд\n🖱 Кликов: {new_clicks}/10\n\n❌ Лимит исчерпан!"
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🖱 Кликнуть", callback_data="click")],
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
            ])
            text = f"🖱 <b>Кликер</b>\n\n✅ Клик засчитан! +{reward} звезды\n" \
                   f"💫 Баланс: {new_balance} звёзд\n🖱 Кликов: {new_clicks}/10\n" \
                   f"⏰ Следующий клик через: {wait_minutes} мин"
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    
    await callback.answer("✅ Клик засчитан!")

@dp.callback_query(F.data == "withdrawal")
async def callback_withdrawal(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
    
    amounts = [15, 25, 50, 100, 1300]
    keyboard_buttons = []
    
    for amount in amounts:
        if user['balance'] >= amount:
            keyboard_buttons.append([InlineKeyboardButton(
                text=f"💫 {amount} звёзд", callback_data=f"withdraw_{amount}"
            )])
        else:
            keyboard_buttons.append([InlineKeyboardButton(
                text=f"❌ {amount} звёзд (недостаточно)", callback_data="insufficient_funds"
            )])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        f"💫 <b>Вывод звёзд</b>\n\n💰 Ваш баланс: {user['balance']} звёзд\n\nВыберите сумму:",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("withdraw_"))
async def callback_withdraw_amount(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    amount = int(callback.data.split("_")[1])
    
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        
        if not user or user['balance'] < amount:
            await callback.answer("❌ Недостаточно средств", show_alert=True)
            return
        
        # Создать заявку на вывод
        withdrawal_id = await conn.fetchval('''
            INSERT INTO withdrawals (user_id, amount) VALUES ($1, $2) RETURNING id
        ''', user_id, amount)
        
        # Списать сумму
        new_balance = float(user['balance']) - amount
        await conn.execute("UPDATE users SET balance = $1 WHERE user_id = $2", new_balance, user_id)
        
        # Отправить в админ-чат
        admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"approve_{withdrawal_id}"),
             InlineKeyboardButton(text="❌ Отклонено", callback_data=f"reject_{withdrawal_id}")]
        ])
        
        admin_text = f"""💫 <b>Новая заявка на вывод</b>

👤 Пользователь: @{user['username'] or 'Не указан'}
🆔 ID: {user_id}
💫 Сумма: {amount} звёзд
💰 Остаток: {new_balance} звёзд
🔗 Ссылка: <a href="tg://user?id={user_id}">Профиль</a>

📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
        
        try:
            await bot.send_message(ADMIN_CHAT_ID, admin_text, reply_markup=admin_keyboard, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки в админ-чат: {e}")
        
        keyboard = create_back_keyboard()
        await callback.message.edit_text(
            f"✅ <b>Заявка отправлена!</b>\n\n💫 Сумма: {amount} звёзд\n"
            f"💰 Ваш баланс: {new_balance} звёзд\n\nЗаявка отправлена администраторам.",
            reply_markup=keyboard, parse_mode="HTML"
        )
    
    await callback.answer()

@dp.callback_query(F.data == "instructions")
async def callback_instructions(callback: types.CallbackQuery):
    keyboard = create_back_keyboard()
    text = """📚 <b>Инструкция по боту</b>

🌟 <b>Как заработать звёзды:</b>

👥 <b>Реферальная система</b>
• Приглашайте друзей по ссылке
• За каждого активного реферала: 2 звезды

🖱 <b>Кликер</b>
• До 10 кликов в день
• За клик: 0.1 звезды
• Время ожидания увеличивается

📋 <b>Задания</b>
• Выполняйте зада��ия от спонсоров
• За задание: 0.3 звезды

📦 <b>Кейсы</b>
• 1 кейс в день при 5 рефералах
• В кейсе: 1-10 звёзд

🎲 <b>Лотереи</b>
• Покупайте билеты
• Выигрывайте призы

🏆 <b>Рейтинги</b>
• Получайте очки за активность
• Топ 5 получают бонусы

💫 <b>Вывод</b>
• От 15 звёзд
• Обработка администраторами"""

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# Заглушки для остальных функций
@dp.callback_query(F.data.in_(["tasks", "ratings", "cases", "lottery", "promo_code"]))
async def callback_placeholder(callback: types.CallbackQuery):
    await callback.answer("🚧 Функция в разработке", show_alert=True)

@dp.callback_query(F.data == "insufficient_funds")
async def callback_insufficient_funds(callback: types.CallbackQuery):
    await callback.answer("❌ Недостаточно средств", show_alert=True)

# Админ функции (заглушки)
@dp.callback_query(F.data.startswith("admin_"))
async def callback_admin_placeholder(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    await callback.answer("🚧 Админ-функция в разработке", show_alert=True)

# ================================
# ЗАПУСК БОТА
# ================================
async def main():
    try:
        await init_db()
        logger.info("🚀 Бот запущен успешно!")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
    finally:
        if db_pool:
            await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
