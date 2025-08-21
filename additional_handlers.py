# ДОБАВЬТЕ ЭТИ ОБРАБОТЧИКИ В bot.py ПЕРЕД ФУНКЦИЕЙ main()

# ================================
# КЛИКЕР
# ================================
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
            seconds = int(time_left.total_seconds() % 60)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🖱 Кликнуть", callback_data="click")],
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(
                f"🖱 <b>Кликер</b>\n\n⏰ До следующего клика: {minutes}м {seconds}с\n"
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
        
        # Обработать к��ик
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

# ================================
# ВЫВОД СРЕДСТВ
# ================================
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
            f"💰 Ва�� баланс: {new_balance} звёзд\n\nЗаявка отправлена администраторам.",
            reply_markup=keyboard, parse_mode="HTML"
        )
    
    await callback.answer()

# ================================
# ЗАДАНИЯ
# ================================
@dp.callback_query(F.data == "tasks")
async def callback_tasks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        completed_count = await conn.fetchval('''
            SELECT COUNT(*) FROM user_tasks 
            WHERE user_id = $1 AND completed = TRUE
        ''', user_id) or 0
        
        next_task = await conn.fetchrow('''
            SELECT t.* FROM tasks t
            LEFT JOIN user_tasks ut ON t.id = ut.task_id AND ut.user_id = $1
            WHERE t.is_active = TRUE AND (ut.completed IS NULL OR ut.completed = FALSE)
            ORDER BY t.created_at
            LIMIT 1
        ''', user_id)
    
    if next_task:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнить задание", url=next_task['url'])],
            [InlineKeyboardButton(text="✅ Проверить выполнение", callback_data=f"check_task_{next_task['id']}")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_task")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            f"📋 <b>Задания</b>\n\n"
            f"📊 Выполнено заданий: {completed_count}\n\n"
            f"📝 <b>Текущее задание:</b>\n"
            f"🎯 {next_task['name']}\n"
            f"💫 Награда: {next_task['reward']} звёзд\n\n"
            f"Нажмите кнопку выше для выполнения задания, затем проверьте выполнение.",
            reply_markup=keyboard, parse_mode="HTML"
        )
    else:
        # Попробовать получить задание от SubGram
        subgram_result = await get_subgram_tasks(user_id, callback.message.chat.id)
        
        if subgram_result.get("status") == "ok" and subgram_result.get("links"):
            link = subgram_result["links"][0]
            
            async with get_db_connection() as conn:
                task_id = await conn.fetchval('''
                    INSERT INTO tasks (name, url, reward, is_subgram, is_active)
                    VALUES ($1, $2, $3, TRUE, TRUE)
                    RETURNING id
                ''', "Подписка на спонсорский канал", link, 0.3)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Выполнить задание", url=link)],
                [InlineKeyboardButton(text="✅ Проверить выполнение", callback_data=f"check_task_{task_id}")],
                [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_task")],
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(
                f"📋 <b>Задания</b>\n\n"
                f"📊 Выполнено заданий: {completed_count}\n\n"
                f"📝 <b>Новое задание от SubGram:</b>\n"
                f"🎯 Подписка на спонсорский канал\n"
                f"💫 Награда: 0.3 звёзд\n\n"
                f"Нажмите кнопку выше для выполнения задания, затем проверьте выполнение.",
                reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            keyboard = create_back_keyboard()
            await callback.message.edit_text(
                f"📋 <b>Задания</b>\n\n"
                f"📊 Выполнено заданий: {completed_count}\n\n"
                f"🎉 Все доступные задания выполнены!\n"
                f"Новые задания появятся позже.",
                reply_markup=keyboard, parse_mode="HTML"
            )
    
    await callback.answer()

@dp.callback_query(F.data.startswith("check_task_"))
async def callback_check_task(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split("_")[2])
    
    async with get_db_connection() as conn:
        existing = await conn.fetchrow('''
            SELECT * FROM user_tasks 
            WHERE user_id = $1 AND task_id = $2
        ''', user_id, task_id)
        
        if existing and existing['completed']:
            await callback.answer("✅ Задание уже выполнено!", show_alert=True)
            return
        
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not task:
            await callback.answer("❌ Задание не найдено", show_alert=True)
            return
        
        # Отметить задание как выполненное
        if existing:
            await conn.execute('''
                UPDATE user_tasks 
                SET completed = TRUE, completed_at = NOW()
                WHERE user_id = $1 AND task_id = $2
            ''', user_id, task_id)
        else:
            await conn.execute('''
                INSERT INTO user_tasks (user_id, task_id, completed, completed_at)
                VALUES ($1, $2, TRUE, NOW())
            ''', user_id, task_id)
        
        # Добавить награду
        await conn.execute('''
            UPDATE users 
            SET balance = balance + $1,
                total_earnings = total_earnings + $1,
                points = points + 1,
                weekly_points = weekly_points + 1
            WHERE user_id = $2
        ''', task['reward'], user_id)
        
        # Проверить реферальный бонус
        user_completed_tasks = await conn.fetchval('''
            SELECT COUNT(*) FROM user_tasks 
            WHERE user_id = $1 AND completed = TRUE
        ''', user_id)
        
        if user_completed_tasks >= 2:
            referral = await conn.fetchrow('''
                SELECT * FROM referrals 
                WHERE referred_id = $1 AND reward_given = FALSE
            ''', user_id)
            
            if referral:
                # Дать бонус рефереру
                await conn.execute('''
                    UPDATE users 
                    SET balance = balance + 2,
                        referral_earnings = referral_earnings + 2,
                        total_earnings = total_earnings + 2,
                        points = points + 2,
                        weekly_points = weekly_points + 2
                    WHERE user_id = $1
                ''', referral['referrer_id'])
                
                # Отметить реферал как награжденный
                await conn.execute('''
                    UPDATE referrals 
                    SET reward_given = TRUE 
                    WHERE referred_id = $1
                ''', user_id)
    
    await callback.answer("✅ Задание выполнено! Награда начислена!", show_alert=True)
    await callback_tasks(callback)

@dp.callback_query(F.data == "skip_task")
async def callback_skip_task(callback: types.CallbackQuery):
    await callback_tasks(callback)

# ================================
# РЕЙТИНГИ
# ================================
@dp.callback_query(F.data == "ratings")
async def callback_ratings(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Общий рейтинг", callback_data="rating_overall")],
        [InlineKeyboardButton(text="📅 Недельный рейтинг", callback_data="rating_weekly")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "🏆 <b>Рейтинги</b>\n\n"
        "Выберите тип рейтинга для просмотра:\n\n"
        "💡 <b>Как получать очки:</b>\n"
        "• 1 реферал = 2 очка\n"
        "• 1 задание = 1 очко\n"
        "• 1 клик = 1 очко\n"
        "• 1 билет лотереи = 1 очко\n\n"
        "🎁 <b>Награды за недельный топ 5:</b>\n"
        "🥇 1 место: 100 звёзд\n"
        "🥈 2 место: 75 звёзд\n"
        "🥉 3 место: 50 звёзд\n"
        "🏅 4 место: 25 звёзд\n"
        "🏅 5 место: 15 звёзд",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "rating_overall")
async def callback_rating_overall(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        top_users = await conn.fetch('''
            SELECT user_id, username, points,
                   ROW_NUMBER() OVER (ORDER BY points DESC) as rank
            FROM users 
            WHERE points > 0
            ORDER BY points DESC 
            LIMIT 10
        ''')
        
        user_rank = await conn.fetchrow('''
            SELECT rank FROM (
                SELECT user_id, ROW_NUMBER() OVER (ORDER BY points DESC) as rank
                FROM users WHERE points > 0
            ) ranked 
            WHERE user_id = $1
        ''', user_id)
    
    rating_text = "🏆 <b>Общий рейтинг по очкам</b>\n\n"
    
    for i, user in enumerate(top_users):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏅"
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        rating_text += f"{medal} {i+1}. {username} - {user['points']} очков\n"
    
    if user_rank:
        rating_text += f"\n📍 <b>Ваша позиция:</b> {user_rank['rank']} место"
    else:
        rating_text += f"\n📍 <b>Ваша позиция:</b> Не в рейтинге"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="rating_overall")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="ratings")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(rating_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "rating_weekly")
async def callback_rating_weekly(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        top_users = await conn.fetch('''
            SELECT user_id, username, weekly_points,
                   ROW_NUMBER() OVER (ORDER BY weekly_points DESC) as rank
            FROM users 
            WHERE weekly_points > 0
            ORDER BY weekly_points DESC 
            LIMIT 10
        ''')
        
        user_rank = await conn.fetchrow('''
            SELECT rank FROM (
                SELECT user_id, ROW_NUMBER() OVER (ORDER BY weekly_points DESC) as rank
                FROM users WHERE weekly_points > 0
            ) ranked 
            WHERE user_id = $1
        ''', user_id)
    
    rating_text = "📅 <b>Недельный рейтинг по очкам</b>\n\n"
    
    rewards = [100, 75, 50, 25, 15]
    for i, user in enumerate(top_users):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏅"
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        reward_text = f" (+{rewards[i]} ⭐)" if i < 5 else ""
        rating_text += f"{medal} {i+1}. {username} - {user['weekly_points']} очков{reward_text}\n"
    
    if user_rank:
        rating_text += f"\n📍 <b>Ваша позиция:</b> {user_rank['rank']} место"
    else:
        rating_text += f"\n📍 <b>Ваша позиция:</b> Не в рейтинге"
    
    rating_text += "\n\n🎁 Награды выдаются каждое воскресенье в 20:00 МСК"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="rating_weekly")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="ratings")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(rating_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ================================
# КЕЙСЫ
# ================================
@dp.callback_query(F.data == "cases")
async def callback_cases(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        if user['daily_case_opened']:
            keyboard = create_back_keyboard()
            await callback.message.edit_text(
                "📦 <b>Кейсы</b>\n\n"
                "❌ Вы уже открыли кейс сегодня!\n"
                "Приходите завтра.",
                reply_markup=keyboard, parse_mode="HTML"
            )
            await callback.answer()
            return
        
        daily_refs = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1 AND DATE(date_referred) = CURRENT_DATE", user_id
        ) or 0
        
        if daily_refs < 5:
            keyboard = create_back_keyboard()
            await callback.message.edit_text(
                f"📦 <b>Кейсы</b>\n\n"
                f"❌ Для открытия кейса нужно пригласить 5 рефералов за день\n"
                f"👥 Рефералов сегодня: {daily_refs}/5",
                reply_markup=keyboard, parse_mode="HTML"
            )
            await callback.answer()
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Открыть кейс", callback_data="open_case")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            f"📦 <b>Кейсы</b>\n\n"
            f"✅ Вы можете открыть кейс!\n"
            f"👥 Рефералов сегодня: {daily_refs}/5\n\n"
            f"💫 В кейсе может выпасть от 1 до 10 звёзд",
            reply_markup=keyboard, parse_mode="HTML"
        )
    
    await callback.answer()

@dp.callback_query(F.data == "open_case")
async def callback_open_case(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with get_db_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        
        if not user or user['daily_case_opened']:
            await callback.answer("❌ Кейс н��доступен", show_alert=True)
            return
        
        daily_refs = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1 AND DATE(date_referred) = CURRENT_DATE", user_id
        ) or 0
        
        if daily_refs < 5:
            await callback.answer("❌ Кейс недоступен", show_alert=True)
            return
        
        reward = random.randint(1, 10)
        
        await conn.execute('''
            UPDATE users 
            SET balance = balance + $1,
                total_earnings = total_earnings + $1,
                daily_case_opened = TRUE
            WHERE user_id = $2
        ''', reward, user_id)
        
        new_balance = float(user['balance']) + reward
    
    keyboard = create_back_keyboard()
    await callback.message.edit_text(
        f"📦 <b>Кейс открыт!</b>\n\n"
        f"🎉 Поздравляем! Вы получили {reward} звёзд!\n"
        f"💫 Ваш баланс: {new_balance} звёзд\n\n"
        f"Следующий кейс можно открыть завтра при условии 5 рефералов.",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer(f"🎉 Вы получили {reward} звёзд!")

# ================================
# ЛОТЕРЕЯ
# ================================
@dp.callback_query(F.data == "lottery")
async def callback_lottery(callback: types.CallbackQuery):
    async with get_db_connection() as conn:
        lottery = await conn.fetchrow('''
            SELECT * FROM lotteries 
            WHERE is_active = TRUE AND ended = FALSE 
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
        
        if not lottery:
            keyboard = create_back_keyboard()
            await callback.message.edit_text(
                "🎲 <b>Лотерея</b>\n\n"
                "❌ Активных лотерей нет\n"
                "Следите за новостями!",
                reply_markup=keyboard, parse_mode="HTML"
            )
            await callback.answer()
            return
        
        remaining = lottery['ticket_count'] - lottery['tickets_sold']
        total_prize = lottery['tickets_sold'] * lottery['ticket_price']
        bot_share = total_prize * lottery['bot_percent'] / 100
        winner_share = total_prize - bot_share
        prize_per_winner = winner_share / lottery['winner_count'] if lottery['winner_count'] > 0 else 0
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎫 Купить билет ({lottery['ticket_price']} звёзд)", 
            callback_data=f"buy_ticket_{lottery['id']}"
        )],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"🎲 <b>Лотерея #{lottery['id']}</b>\n\n"
        f"🎫 Цена билета: {lottery['ticket_price']} звёзд\n"
        f"📊 Продано билетов: {lottery['tickets_sold']}/{lottery['ticket_count']}\n"
        f"🎯 Осталось билетов: {remaining}\n"
        f"🏆 Количество победителей: {lottery['winner_count']}\n"
        f"💰 Общий призовой фонд: {total_prize} звёзд\n"
        f"💫 Приз каждому победителю: ~{prize_per_winner:.1f} звёзд\n\n"
        f"Лотерея завершится, когда все билеты будут проданы.",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_ticket_"))
async def callback_buy_ticket(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lottery_id = int(callback.data.split("_")[2])
    
    async with get_db_connection() as conn:
        lottery = await conn.fetchrow("SELECT * FROM lotteries WHERE id = $1", lottery_id)
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
        
        if not lottery or not user:
            await callback.answer("❌ Ошибка", show_alert=True)
            return
        
        if lottery['ended'] or lottery['tickets_sold'] >= lottery['ticket_count']:
            await callback.answer("❌ Лотерея завершена", show_alert=True)
            return
        
        if user['balance'] < lottery['ticket_price']:
            await callback.answer("❌ Недостаточно средств", show_alert=True)
            return
        
        ticket_number = lottery['tickets_sold'] + 1
        
        await conn.execute('''
            INSERT INTO lottery_tickets (lottery_id, user_id, ticket_number)
            VALUES ($1, $2, $3)
        ''', lottery_id, user_id, ticket_number)
        
        await conn.execute('''
            UPDATE lotteries 
            SET tickets_sold = tickets_sold + 1
            WHERE id = $1
        ''', lottery_id)
        
        await conn.execute('''
            UPDATE users 
            SET balance = balance - $1,
                points = points + 1,
                weekly_points = weekly_points + 1
            WHERE user_id = $2
        ''', lottery['ticket_price'], user_id)
        
        if ticket_number >= lottery['ticket_count']:
            await end_lottery(lottery_id)
    
    await callback.answer(f"✅ Билет #{ticket_number} куплен!", show_alert=True)
    await callback_lottery(callback)

async def end_lottery(lottery_id: int):
    """Завершить лотерею и выбрать победителей"""
    async with get_db_connection() as conn:
        lottery = await conn.fetchrow("SELECT * FROM lotteries WHERE id = $1", lottery_id)
        
        if not lottery or lottery['ended']:
            return
        
        tickets = await conn.fetch('''
            SELECT * FROM lottery_tickets 
            WHERE lottery_id = $1 
            ORDER BY ticket_number
        ''', lottery_id)
        
        if len(tickets) == 0:
            return
        
        winners = random.sample(tickets, min(lottery['winner_count'], len(tickets)))
        
        total_prize = lottery['tickets_sold'] * lottery['ticket_price']
        bot_share = total_prize * lottery['bot_percent'] / 100
        winner_share = total_prize - bot_share
        prize_per_winner = winner_share / len(winners)
        
        for winner in winners:
            await conn.execute('''
                UPDATE users 
                SET balance = balance + $1
                WHERE user_id = $2
            ''', prize_per_winner, winner['user_id'])
        
        await conn.execute('''
            UPDATE lotteries 
            SET ended = TRUE, ended_at = NOW()
            WHERE id = $1
        ''', lottery_id)
        
        winners_text = "\n".join([f"🎫 Билет #{w['ticket_number']} - ID: {w['user_id']} - {prize_per_winner:.1f} звёзд" for w in winners])
        
        result_text = f"""🎲 <b>Лотерея #{lottery_id} завершена!</b>

📊 Всего билетов: {lottery['tickets_sold']}
💰 Общий фонд: {total_prize} звёзд
🤖 Доля бота: {bot_share:.1f} звёзд
🏆 Призовой фонд: {winner_share:.1f} звёзд

🎉 <b>Победители:</b>
{winners_text}"""
        
        try:
            await bot.send_message(PAYMENTS_CHAT_ID, result_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки результатов лотереи: {e}")

# ================================
# ПРОМОКОДЫ
# ================================
@dp.callback_query(F.data == "promo_code")
async def callback_promo_code(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo_code)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к профилю", callback_data="profile")]
    ])
    
    await callback.message.edit_text(
        "🎫 <b>Промокод</b>\n\n"
        "Введите промокод для получения награды:",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@dp.message(UserStates.waiting_for_promo_code)
async def handle_promo_code_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    promo_code = message.text.strip().upper()
    
    async with get_db_connection() as conn:
        promo = await conn.fetchrow('''
            SELECT * FROM promo_codes 
            WHERE code = $1 AND is_active = TRUE
        ''', promo_code)
        
        if not promo:
            keyboard = create_profile_keyboard()
            await message.answer(
                "❌ <b>Промокод не найден или неактивен</b>\n\n"
                "Проверьте правильность ввода и попробуйте снова.",
                reply_markup=keyboard, parse_mode="HTML"
            )
            await state.clear()
            return
        
        if promo['current_uses'] >= promo['max_uses']:
            keyboard = create_profile_keyboard()
            await message.answer(
                "❌ <b>Промокод больше недоступен</b>\n\n"
                "Лимит использований исчерпан.",
                reply_markup=keyboard, parse_mode="HTML"
            )
            await state.clear()
            return
        
        existing_use = await conn.fetchrow('''
            SELECT * FROM promo_uses 
            WHERE user_id = $1 AND promo_id = $2
        ''', user_id, promo['id'])
        
        if existing_use:
            keyboard = create_profile_keyboard()
            await message.answer(
                "❌ <b>Промокод уже использован</b>\n\n"
                "Вы уже использовали этот промокод ранее.",
                reply_markup=keyboard, parse_mode="HTML"
            )
            await state.clear()
            return
        
        await conn.execute('''
            INSERT INTO promo_uses (user_id, promo_id)
            VALUES ($1, $2)
        ''', user_id, promo['id'])
        
        await conn.execute('''
            UPDATE promo_codes 
            SET current_uses = current_uses + 1
            WHERE id = $1
        ''', promo['id'])
        
        await conn.execute('''
            UPDATE users 
            SET balance = balance + $1,
                total_earnings = total_earnings + $1
            WHERE user_id = $2
        ''', promo['reward'], user_id)
        
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
    
    keyboard = create_profile_keyboard()
    await message.answer(
        f"🎉 <b>Промокод успешно использован!</b>\n\n"
        f"🎫 Промокод: {promo_code}\n"
        f"💫 Награда: {promo['reward']} звёзд\n"
        f"💰 Ваш баланс: {user['balance']} звёзд",
        reply_markup=keyboard, parse_mode="HTML"
    )
    
    await state.clear()

# ================================
# ИНСТРУКЦИЯ
# ================================
@dp.callback_query(F.data == "instructions")
async def callback_instructions(callback: types.CallbackQuery):
    keyboard = create_back_keyboard()
    text = """📚 <b>Инструкция по боту</b>

🌟 <b>Как заработать звёзды:</b>

👥 <b>Реферальная система</b>
• Приглашайте друзей по ссыл��е
• За каждого активного реферала: 2 звезды

🖱 <b>Кликер</b>
• До 10 кликов в день
• За клик: 0.1 звезды
• Время ожидания увеличивается

📋 <b>Задания</b>
• Выполняйте задания от спонсоров
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

# Заглушки
@dp.callback_query(F.data == "insufficient_funds")
async def callback_insufficient_funds(callback: types.CallbackQuery):
    await callback.answer("❌ Недостаточно средств", show_alert=True)

@dp.callback_query(F.data.startswith("admin_"))
async def callback_admin_placeholder(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    await callback.answer("🚧 Админ-функция в разработке", show_alert=True)
