import telebot
from telebot import types
import sqlite3
import uuid
from datetime import datetime, timedelta
import logging
import time
import os
import re
from flask import Flask, request

# ====================== НАСТРОЙКИ ======================
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    TOKEN = "8645055063:AAGUJacLUVbWMy2QXHJoek46_4-YCqgjt0E"

bot = telebot.TeleBot(TOKEN, parse_mode='HTML')
app = Flask(__name__)

ADMIN_IDS = [2132292931]
CHANNEL_ID = -1002294990255

COOLDOWN_MINUTES = 30
MAX_SUBSCRIPTIONS = 5
MAX_PHOTOS = 10
MAX_VIDEOS = 3

MAINTENANCE_MODE = False
MAINTENANCE_REASON = ""

# ====================== СОСТОЯНИЯ ======================
user_state = {}
subscription_state = {}
admin_state = {}
broadcast_data = {}

# ====================== ЛОГИРОВАНИЕ ======================
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# ====================== БАЗА ДАННЫХ ======================
DB_PATH = 'ads.db'

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_ads (
        ad_id TEXT PRIMARY KEY,
        user_id INTEGER,
        username TEXT,
        category TEXT,
        subcategory TEXT,
        ad_type TEXT,
        title TEXT,
        description TEXT,
        price TEXT,
        photo_ids TEXT,
        video_ids TEXT,
        contact TEXT,
        date TEXT,
        status TEXT DEFAULT 'pending'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_cooldown (
        user_id INTEGER PRIMARY KEY,
        last_ad_time TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        ad_type TEXT,
        created_at TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
        user_id INTEGER PRIMARY KEY,
        reason TEXT,
        banned_until TEXT,
        banned_by INTEGER,
        created_at TEXT
    )''')
    
    conn.commit()
    conn.close()

init_db()

# ====================== ВЕБХУК ======================
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")
if WEBHOOK_URL:
    WEBHOOK_URL = f"{WEBHOOK_URL}/webhook"
else:
    WEBHOOK_URL = "https://YOUR-APP.onrender.com/webhook"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Bad Request', 400

@app.route('/')
def index():
    return 'Bot is running!', 200

# ====================== ФУНКЦИИ НАКАЗАНИЙ ======================
def is_user_banned(user_id):
    if user_id in ADMIN_IDS:
        return False
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT banned_until FROM banned_users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result and result[0]:
        try:
            banned_until = datetime.fromisoformat(result[0])
            if datetime.now() < banned_until:
                return True
            else:
                conn = get_db()
                c = conn.cursor()
                c.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()
        except:
            pass
    return False

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "Нет доступа!")
        return
    
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            bot.send_message(message.chat.id, "Использование: /ban @username [причина]")
            return
        
        username = parts[1].replace('@', '')
        reason = parts[2] if len(parts) > 2 else "Нарушение правил"
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM user_ads WHERE username = ? LIMIT 1", (username,))
        user_data = c.fetchone()
        
        if not user_data:
            bot.send_message(message.chat.id, f"Пользователь @{username} не найден!")
            conn.close()
            return
        
        user_id = user_data[0]
        banned_until = (datetime.now() + timedelta(days=365*10)).isoformat()
        
        c.execute("INSERT OR REPLACE INTO banned_users (user_id, reason, banned_until, banned_by, created_at) VALUES (?, ?, ?, ?, ?)",
                  (user_id, reason, banned_until, message.from_user.id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"Пользователь @{username} забанен навсегда!\nПричина: {reason}")
        
        try:
            bot.send_message(user_id, f"<b>Вы забанены!</b>\n\nПричина: {reason}\nВы не можете использовать бота.", parse_mode='HTML')
        except:
            pass
            
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "Нет доступа!")
        return
    
    try:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 3:
            bot.send_message(message.chat.id, "Использование: /mute @username время(часы) [причина]")
            return
        
        username = parts[1].replace('@', '')
        hours = int(parts[2])
        reason = parts[3] if len(parts) > 3 else "Нарушение правил"
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM user_ads WHERE username = ? LIMIT 1", (username,))
        user_data = c.fetchone()
        
        if not user_data:
            bot.send_message(message.chat.id, f"Пользователь @{username} не найден!")
            conn.close()
            return
        
        user_id = user_data[0]
        banned_until = (datetime.now() + timedelta(hours=hours)).isoformat()
        
        c.execute("INSERT OR REPLACE INTO banned_users (user_id, reason, banned_until, banned_by, created_at) VALUES (?, ?, ?, ?, ?)",
                  (user_id, reason, banned_until, message.from_user.id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"Пользователь @{username} замьючен на {hours} часов!\nПричина: {reason}")
        
        try:
            bot.send_message(user_id, f"<b>Вы замьючены!</b>\n\nПричина: {reason}\nВремя: {hours} часов", parse_mode='HTML')
        except:
            pass
            
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "Нет доступа!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "Использование: /unban @username")
            return
        
        username = parts[1].replace('@', '')
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM user_ads WHERE username = ? LIMIT 1", (username,))
        user_data = c.fetchone()
        
        if not user_data:
            bot.send_message(message.chat.id, f"Пользователь @{username} не найден!")
            conn.close()
            return
        
        user_id = user_data[0]
        
        c.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"Пользователь @{username} разбанен!")
        
        try:
            bot.send_message(user_id, f"<b>Вы разбанены!</b>\n\nВы снова можете использовать бота.", parse_mode='HTML')
        except:
            pass
            
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

# ====================== ГЛАВНОЕ МЕНЮ ======================
def main_menu(is_admin=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("Подать объявление")
    btn2 = types.KeyboardButton("Мои объявления")
    btn3 = types.KeyboardButton("Мои подписки")
    btn4 = types.KeyboardButton("Поддержка")
    
    if is_admin:
        btn5 = types.KeyboardButton("Админ-панель")
        markup.add(btn1, btn2, btn3, btn4, btn5)
    else:
        markup.add(btn1, btn2, btn3, btn4)
    
    return markup

# ====================== ПРИВЕТСТВИЕ ======================
@bot.message_handler(commands=['start'])
def start_command(message):
    if is_user_banned(message.from_user.id):
        bot.send_message(message.chat.id, "Вы забанены и не можете использовать бота!")
        return
    
    if MAINTENANCE_MODE and message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, f"Бот на тех работах.\nПричина: {MAINTENANCE_REASON}")
        return

    caption = """
BLACKBERRY MARKET | 05

Добро пожаловать!

----------------------------------------
Автомобили (Вертолёты, Мотоциклы)
Скины
Аксессуары
Недвижимость
Другое
----------------------------------------

Правила подачи объявления:
- Фото (до 10 шт) или видео (до 3 шт)
- ДОГОВОРНАЯ ЦЕНА ЗАПРЕЩЕНА!
- Указывайте точный контакт

BlackBerry Market | 05 — честность и качество!
    """.strip()

    is_admin = message.from_user.id in ADMIN_IDS
    bot.send_message(message.chat.id, caption, reply_markup=main_menu(is_admin))

# ====================== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ======================
@bot.message_handler(func=lambda message: True, content_types=['text'])
def text_handler(message):
    if is_user_banned(message.from_user.id):
        bot.send_message(message.chat.id, "Вы забанены и не можете использовать бота!")
        return
    
    if MAINTENANCE_MODE and message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, f"Бот на обслуживании.\nПричина: {MAINTENANCE_REASON}")
        return
    
    if message.from_user.id in user_state:
        process_ad_steps(message)
        return
    
    text = message.text
    
    if text == "Админ-панель":
        admin_panel(message)
    elif text == "Подать объявление":
        start_ad(message)
    elif text == "Мои объявления":
        show_my_ads(message)
    elif text == "Мои подписки":
        show_subscriptions(message)
    elif text == "Поддержка":
        support_menu(message)

# ====================== ПОДАЧА ОБЪЯВЛЕНИЯ ======================
def start_ad(message):
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        bot.send_message(message.chat.id, "Вы забанены и не можете подавать объявления!")
        return
    
    if user_id not in ADMIN_IDS:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT last_ad_time FROM user_cooldown WHERE user_id = ?", (user_id,))
        cooldown = c.fetchone()
        conn.close()
        
        if cooldown and cooldown[0]:
            try:
                last = datetime.fromisoformat(cooldown[0])
                if (datetime.now() - last).total_seconds() < COOLDOWN_MINUTES * 60:
                    remaining = int((COOLDOWN_MINUTES * 60 - (datetime.now() - last).total_seconds()) / 60)
                    bot.send_message(message.chat.id, f"Подождите {remaining} минут перед следующей подачей.")
                    return
            except:
                pass

    user_state[user_id] = {"step": "category"}
    markup = types.InlineKeyboardMarkup(row_width=2)
    cats = ["Автомобили", "Скины", "Аксессуары", "Недвижимость", "Другое"]
    for cat in cats:
        markup.add(types.InlineKeyboardButton(cat, callback_data=f"cat_{cat}"))
    
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

def process_ad_steps(message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    if not state:
        return

    step = state.get("step")
    
    if step == "title":
        if len(message.text) < 3:
            bot.send_message(message.chat.id, "Название слишком короткое (минимум 3 символа)")
            return
        state["title"] = message.text
        state["step"] = "description"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Пропустить описание", callback_data="skip_description"))
        bot.send_message(message.chat.id, "Введите описание товара (или нажмите «Пропустить»):", reply_markup=markup)
    
    elif step == "description":
        if message.text == "Пропустить описание":
            state["description"] = ""
        else:
            if len(message.text) < 5:
                bot.send_message(message.chat.id, "Описание слишком короткое (минимум 5 символов) или нажмите «Пропустить»")
                return
            state["description"] = message.text
        state["step"] = "price"
        
        price_warning = """
ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ!

ДОГОВОРНАЯ ЦЕНА ЗАПРЕЩЕНА!

Указывайте только точную сумму цифрами.

Правильные примеры:
- 1000
- 5000
- 15000

Неправильные примеры:
- Договорная
- 1000 руб
- Дорого

Введите цену (только цифры):
        """.strip()
        
        bot.send_message(message.chat.id, price_warning)
    
    elif step == "price":
        if not message.text.isdigit():
            bot.send_message(message.chat.id, "Цена должна состоять только из цифр! Договорная цена ЗАПРЕЩЕНА!\n\nВведите цену (только цифры):")
            return
        if int(message.text) <= 0:
            bot.send_message(message.chat.id, "Цена должна быть больше 0!")
            return
        state["price"] = message.text
        state["step"] = "contact"
        bot.send_message(message.chat.id, "Укажите контакт для связи:")
    
    elif step == "contact":
        if len(message.text) < 2:
            bot.send_message(message.chat.id, "Контакт слишком короткий")
            return
        state["contact"] = message.text
        state["step"] = "media"
        state["photos"] = []
        state["videos"] = []
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("ПРЕДПРОСМОТР", callback_data="preview_ad"))
        
        bot.send_message(message.chat.id, 
            f"Загрузите медиафайлы\n\n"
            f"Фото: до {MAX_PHOTOS} шт.\n"
            f"Видео: до {MAX_VIDEOS} шт.\n\n"
            f"Просто отправьте фото или видео.\n"
            f"Когда закончите, нажмите ПРЕДПРОСМОТР",
            reply_markup=markup)

# ====================== ОБРАБОТЧИК ФОТО И ВИДЕО ======================
@bot.message_handler(content_types=['photo', 'video'])
def media_handler(message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    if not state or state.get("step") != "media":
        return
    
    if message.photo:
        if len(state["photos"]) >= MAX_PHOTOS:
            bot.send_message(message.chat.id, f"Максимум {MAX_PHOTOS} фото! Нажмите ПРЕДПРОСМОТР")
            return
        state["photos"].append(message.photo[-1].file_id)
        remaining = MAX_PHOTOS - len(state["photos"])
        bot.send_message(message.chat.id, f"Фото {len(state['photos'])}/{MAX_PHOTOS} добавлено! Осталось: {remaining}")
    
    elif message.video:
        if len(state["videos"]) >= MAX_VIDEOS:
            bot.send_message(message.chat.id, f"Максимум {MAX_VIDEOS} видео! Нажмите ПРЕДПРОСМОТР")
            return
        state["videos"].append(message.video.file_id)
        remaining = MAX_VIDEOS - len(state["videos"])
        bot.send_message(message.chat.id, f"Видео {len(state['videos'])}/{MAX_VIDEOS} добавлено! Осталось: {remaining}")

# ====================== ОБРАБОТЧИК CALLBACK ЗАПРОСОВ ======================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    
    if data.startswith("cat_"):
        category = data[4:]
        
        if category == "Автомобили":
            user_state[user_id] = {"step": "subcategory", "category": category}
            markup = types.InlineKeyboardMarkup(row_width=2)
            subcats = ["Вертолёты", "Мотоциклы", "Автомобили", "Другое"]
            for subcat in subcats:
                markup.add(types.InlineKeyboardButton(subcat, callback_data=f"subcat_{subcat}"))
            bot.edit_message_text("Выберите подкатегорию:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            user_state[user_id] = {"step": "type", "category": category, "subcategory": None}
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("Продам", callback_data="type_Продам"),
                types.InlineKeyboardButton("Куплю", callback_data="type_Куплю"),
                types.InlineKeyboardButton("Обмен", callback_data="type_Обмен")
            )
            bot.edit_message_text(f"Категория: <b>{category}</b>\nВыберите тип:", 
                                  call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='HTML')
        bot.answer_callback_query(call.id)
    
    elif data.startswith("subcat_"):
        subcategory = data[7:]
        state = user_state.get(user_id)
        if state and state.get("step") == "subcategory":
            state["subcategory"] = subcategory
            state["step"] = "type"
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("Продам", callback_data="type_Продам"),
                types.InlineKeyboardButton("Куплю", callback_data="type_Куплю"),
                types.InlineKeyboardButton("Обмен", callback_data="type_Обмен")
            )
            bot.edit_message_text(f"Категория: <b>{state['category']}</b>\nПодкатегория: {subcategory}\nВыберите тип:", 
                                  call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='HTML')
        bot.answer_callback_query(call.id)
    
    elif data.startswith("type_"):
        ad_type = data[5:]
        state = user_state.get(user_id)
        if state:
            state["ad_type"] = ad_type
            state["step"] = "title"
            bot.send_message(call.message.chat.id, "Введите название объявления:")
        bot.answer_callback_query(call.id)
    
    elif data == "skip_description":
        state = user_state.get(user_id)
        if state and state.get("step") == "description":
            state["description"] = ""
            state["step"] = "price"
            price_warning = """
ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ!

ДОГОВОРНАЯ ЦЕНА ЗАПРЕЩЕНА!

Указывайте только точную сумму цифрами.

Правильные примеры:
- 1000
- 5000
- 15000

Неправильные примеры:
- Договорная
- 1000 руб
- Дорого

Введите цену (только цифры):
            """.strip()
            bot.send_message(call.message.chat.id, price_warning)
        bot.answer_callback_query(call.id)
    
    elif data == "preview_ad":
        state = user_state.get(user_id)
        if not state or state.get("step") != "media":
            bot.answer_callback_query(call.id, "Сначала заполните все поля!")
            return
        
        if len(state.get("photos", [])) == 0 and len(state.get("videos", [])) == 0:
            bot.answer_callback_query(call.id, "Добавьте хотя бы одно фото или видео!", show_alert=True)
            return
        
        subcat_text = f"\nПодкатегория: {state['subcategory']}" if state.get('subcategory') else ""
        desc_text = f"\nОписание: {state.get('description', 'Не указано')[:300]}" if state.get('description') else ""
        
        text = f"""
ПРЕДПРОСМОТР
----------------------------------------

Категория: {state['category']}{subcat_text}
Тип: {state['ad_type']}
Название: {state['title']}{desc_text}
Цена: {state['price']} руб
Контакт: <code>{state['contact']}</code>

Медиафайлы:
- Фото: {len(state['photos'])} шт.
- Видео: {len(state['videos'])} шт.
----------------------------------------

Проверьте правильность данных!
        """.strip()
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("ОТПРАВИТЬ НА МОДЕРАЦИЮ", callback_data="submit_to_moderation"),
            types.InlineKeyboardButton("РЕДАКТИРОВАТЬ", callback_data="edit_ad"),
            types.InlineKeyboardButton("ДОБАВИТЬ МЕДИА", callback_data="add_more_media")
        )
        
        if state.get('photos'):
            bot.send_photo(call.message.chat.id, state['photos'][0], caption=text, parse_mode='HTML', reply_markup=markup)
        elif state.get('videos'):
            bot.send_video(call.message.chat.id, state['videos'][0], caption=text, parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        
        bot.answer_callback_query(call.id)
    
    elif data == "add_more_media":
        state = user_state.get(user_id)
        if state:
            state["step"] = "media"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("ПРЕДПРОСМОТР", callback_data="preview_ad"))
            bot.send_message(call.message.chat.id, "Продолжайте отправлять фото или видео. Когда закончите, нажмите ПРЕДПРОСМОТР", reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif data == "submit_to_moderation":
        state = user_state.get(user_id)
        if not state:
            bot.answer_callback_query(call.id, "Ошибка!")
            return
        
        ad_id = str(uuid.uuid4())
        
        conn = get_db()
        c = conn.cursor()
        c.execute("""INSERT INTO user_ads 
                     (ad_id, user_id, username, category, subcategory, ad_type, title, description, price, photo_ids, video_ids, contact, date, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (ad_id, user_id, call.from_user.username or "NoUsername",
                   state["category"], state.get("subcategory"), state["ad_type"], state["title"],
                   state.get("description", ""), state["price"], 
                   ",".join(state["photos"]) if state["photos"] else "",
                   ",".join(state["videos"]) if state["videos"] else "",
                   state["contact"],
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pending"))
        conn.commit()
        conn.close()
        
        if user_id not in ADMIN_IDS:
            conn = get_db()
            c = conn.cursor()
            c.execute("REPLACE INTO user_cooldown (user_id, last_ad_time) VALUES (?, ?)",
                      (user_id, datetime.now().isoformat()))
            conn.commit()
            conn.close()
        
        bot.send_message(call.message.chat.id, 
            "Объявление отправлено на модерацию!\n\n"
            "Обычно модерация занимает до 24 часов.\n"
            "Вы получите уведомление о решении.\n\n"
            "Спасибо!")
        
        category = state["category"]
        ad_type = state["ad_type"]
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM subscriptions WHERE category = ? AND (ad_type IS NULL OR ad_type = ?) AND user_id != ?", 
                  (category, ad_type, user_id))
        subscribers = c.fetchall()
        conn.close()
        
        for subscriber in subscribers:
            try:
                notify_text = f"""
НОВОЕ ОБЪЯВЛЕНИЕ ПО ПОДПИСКЕ!
----------------------------------------

Категория: {category}
Тип: {ad_type}
Название: {state['title']}
Цена: {state['price']} руб

Объявление отправлено на модерацию.
Ожидайте публикации в канале!
                """.strip()
                bot.send_message(subscriber[0], notify_text)
            except:
                pass
        
        subcat_text = f"\nПодкатегория: {state['subcategory']}" if state.get('subcategory') else ""
        
        admin_notify = f"""
НОВОЕ ОБЪЯВЛЕНИЕ НА МОДЕРАЦИЮ!
----------------------------------------

ID: <code>{ad_id}</code>
Пользователь: @{call.from_user.username or user_id}
Категория: {state['category']}{subcat_text}
Тип: {state['ad_type']}
Название: {state['title']}
Описание: {state.get('description', 'Не указано')[:200]}
Цена: {state['price']} руб
Контакт: {state['contact']}
Фото: {len(state['photos'])} шт.
Видео: {len(state['videos'])} шт.
----------------------------------------
Действия:
        """.strip()
        
        markup_admin = types.InlineKeyboardMarkup(row_width=2)
        markup_admin.add(
            types.InlineKeyboardButton("ОДОБРИТЬ", callback_data=f"approve_{ad_id}"),
            types.InlineKeyboardButton("ОТКЛОНИТЬ", callback_data=f"reject_{ad_id}"),
            types.InlineKeyboardButton("ПРОСМОТР", callback_data=f"view_{ad_id}")
        )
        
        for admin in ADMIN_IDS:
            try:
                bot.send_message(admin, admin_notify, parse_mode='HTML', reply_markup=markup_admin)
            except:
                pass
        
        del user_state[user_id]
        bot.answer_callback_query(call.id, "Отправлено на модерацию!")
    
    elif data == "edit_ad":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("Изменить название", callback_data="edit_title"),
            types.InlineKeyboardButton("Изменить описание", callback_data="edit_description"),
            types.InlineKeyboardButton("Изменить цену", callback_data="edit_price"),
            types.InlineKeyboardButton("Изменить контакт", callback_data="edit_contact"),
            types.InlineKeyboardButton("Назад к предпросмотру", callback_data="preview_ad")
        )
        bot.send_message(call.message.chat.id, "Что хотите изменить?", reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif data == "edit_title":
        state = user_state.get(user_id)
        if state:
            state["step"] = "title"
            bot.send_message(call.message.chat.id, "Введите новое название:")
        bot.answer_callback_query(call.id)
    
    elif data == "edit_description":
        state = user_state.get(user_id)
        if state:
            state["step"] = "description"
            bot.send_message(call.message.chat.id, "Введите новое описание:")
        bot.answer_callback_query(call.id)
    
    elif data == "edit_price":
        state = user_state.get(user_id)
        if state:
            state["step"] = "price"
            bot.send_message(call.message.chat.id, "Введите новую цену (только цифры):")
        bot.answer_callback_query(call.id)
    
    elif data == "edit_contact":
        state = user_state.get(user_id)
        if state:
            state["step"] = "contact"
            bot.send_message(call.message.chat.id, "Введите новый контакт:")
        bot.answer_callback_query(call.id)
    
    elif data.startswith("approve_"):
        if call.from_user.id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        ad_id = data.replace("approve_", "")
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, title, price, category, ad_type FROM user_ads WHERE ad_id = ?", (ad_id,))
        ad = c.fetchone()
        
        if ad:
            c.execute("UPDATE user_ads SET status = 'approved' WHERE ad_id = ?", (ad_id,))
            conn.commit()
            
            user_notify = f"""
ОБЪЯВЛЕНИЕ ОДОБРЕНО!
----------------------------------------

Название: {ad[1]}
Цена: {ad[2]} руб
Категория: {ad[3]}
Тип: {ad[4]}

Поздравляем!
Ваше объявление прошло модерацию и опубликовано в нашем канале!
            """.strip()
            
            try:
                bot.send_message(ad[0], user_notify)
            except:
                pass
            
            try:
                bot.edit_message_text(f"ОДОБРЕНО\nID: {ad_id}", call.message.chat.id, call.message.message_id)
            except:
                pass
            
            if CHANNEL_ID:
                publish_to_channel(ad_id)
        
        conn.close()
        bot.answer_callback_query(call.id, "Одобрено!")
    
    elif data.startswith("reject_"):
        if call.from_user.id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        ad_id = data.replace("reject_", "")
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, title FROM user_ads WHERE ad_id = ?", (ad_id,))
        ad = c.fetchone()
        
        if ad:
            c.execute("UPDATE user_ads SET status = 'rejected' WHERE ad_id = ?", (ad_id,))
            conn.commit()
            
            user_notify = f"""
ОБЪЯВЛЕНИЕ ОТКЛОНЕНО!
----------------------------------------

Название: {ad[1]}

Возможные причины:
- Договорная цена
- Нет фото/видео
- Неполное описание
- Нарушение правил

Вы можете подать объявление заново, исправив ошибки.
            """.strip()
            
            try:
                bot.send_message(ad[0], user_notify)
            except:
                pass
            
            try:
                bot.edit_message_text(f"ОТКЛОНЕНО\nID: {ad_id}", call.message.chat.id, call.message.message_id)
            except:
                pass
        
        conn.close()
        bot.answer_callback_query(call.id, "Отклонено!")
    
    elif data.startswith("view_"):
        if call.from_user.id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        ad_id = data.replace("view_", "")
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM user_ads WHERE ad_id = ?", (ad_id,))
        ad = c.fetchone()
        conn.close()
        
        if ad:
            text = f"""
ПОЛНЫЙ ПРОСМОТР
----------------------------------------

ID: <code>{ad[0]}</code>
Пользователь: @{ad[2] or ad[1]}
Категория: {ad[3]}
Подкатегория: {ad[4] if ad[4] else 'Нет'}
Тип: {ad[5]}
Название: {ad[6]}
Описание: {ad[7][:300] if ad[7] else 'Не указано'}
Цена: {ad[8]} руб
Контакт: <code>{ad[11]}</code>
Дата: {ad[12]}
Фото: {len(ad[9].split(',')) if ad[9] else 0} шт.
Видео: {len(ad[10].split(',')) if ad[10] else 0} шт.
            """.strip()
            
            bot.send_message(call.message.chat.id, text, parse_mode='HTML')
        
        bot.answer_callback_query(call.id)
    
    elif data == "sub_new":
        subscription_state[user_id] = {"step": "category"}
        markup = types.InlineKeyboardMarkup(row_width=2)
        cats = ["Автомобили", "Скины", "Аксессуары", "Недвижимость", "Другое"]
        for cat in cats:
            markup.add(types.InlineKeyboardButton(cat, callback_data=f"sub_cat_{cat}"))
        bot.send_message(call.message.chat.id, "Выберите категорию:", reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif data.startswith("sub_cat_"):
        category = data[8:]
        subscription_state[user_id] = {"category": category, "step": "type"}
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("Продам", callback_data="sub_type_Продам"),
            types.InlineKeyboardButton("Куплю", callback_data="sub_type_Куплю"),
            types.InlineKeyboardButton("Обмен", callback_data="sub_type_Обмен"),
            types.InlineKeyboardButton("Любой тип", callback_data="sub_type_Любой")
        )
        bot.send_message(call.message.chat.id, f"Категория: {category}\n\nВыберите тип:", reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif data.startswith("sub_type_"):
        ad_type = data[9:]
        if ad_type == "Любой":
            ad_type = None
        
        category = subscription_state[user_id].get("category")
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id = ?", (user_id,))
        count = c.fetchone()[0]
        
        if count >= MAX_SUBSCRIPTIONS:
            bot.send_message(call.message.chat.id, f"У вас уже {MAX_SUBSCRIPTIONS} подписок.")
            conn.close()
            del subscription_state[user_id]
            return
        
        c.execute("""INSERT INTO subscriptions (user_id, category, ad_type, created_at) 
                     VALUES (?, ?, ?, ?)""",
                  (user_id, category, ad_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        type_text = ad_type if ad_type else "все типы"
        bot.send_message(call.message.chat.id, f"Подписка на <b>{category}</b> ({type_text}) создана!\n\nВы будете получать уведомления о новых объявлениях.")
        del subscription_state[user_id]
        bot.answer_callback_query(call.id)
    
    elif data.startswith("sub_del_"):
        sub_id = int(data[7:])
        user_id = call.from_user.id
        
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM subscriptions WHERE id = ? AND user_id = ?", (sub_id, user_id))
        conn.commit()
        conn.close()
        
        bot.answer_callback_query(call.id, "Подписка удалена!")
        show_subscriptions(call.message)
    
    elif data.startswith("del_ad_"):
        ad_id = data.replace("del_ad_", "")
        user_id = call.from_user.id
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM user_ads WHERE ad_id = ?", (ad_id,))
        ad = c.fetchone()
        
        if ad and ad[0] == user_id:
            c.execute("DELETE FROM user_ads WHERE ad_id = ?", (ad_id,))
            conn.commit()
            bot.answer_callback_query(call.id, "Объявление удалено!")
            show_my_ads(call.message)
        else:
            bot.answer_callback_query(call.id, "Нет доступа!")
        conn.close()
    
    elif data == "admin_moderate":
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT ad_id, title, user_id, username, date FROM user_ads WHERE status = 'pending' ORDER BY date DESC")
        ads = c.fetchall()
        conn.close()
        
        if not ads:
            bot.send_message(call.message.chat.id, "Нет объявлений на модерации.")
            bot.answer_callback_query(call.id)
            return
        
        for ad_id, title, user_id, username, date in ads:
            text = f"""
ОБЪЯВЛЕНИЕ НА МОДЕРАЦИИ
----------------------------------------

Название: {title}
Пользователь: @{username or user_id}
ID: <code>{ad_id}</code>
            """.strip()
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("Одобрить", callback_data=f"approve_{ad_id}"),
                types.InlineKeyboardButton("Отклонить", callback_data=f"reject_{ad_id}"),
                types.InlineKeyboardButton("Просмотр", callback_data=f"view_{ad_id}")
            )
            
            bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        
        bot.answer_callback_query(call.id)
    
    elif data == "admin_stats":
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_ads")
        total_ads = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM user_ads WHERE status = 'pending'")
        pending_ads = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM user_ads WHERE status = 'approved'")
        approved_ads = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT user_id) FROM user_ads")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM subscriptions")
        total_subscriptions = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM banned_users")
        total_banned = c.fetchone()[0]
        conn.close()
        
        text = f"""
СТАТИСТИКА БОТА
----------------------------------------

Всего объявлений: {total_ads}
На модерации: {pending_ads}
Одобрено: {approved_ads}
Всего пользователей: {total_users}
Подписок: {total_subscriptions}
Забанено: {total_banned}
        """.strip()
        
        bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)
    
    elif data == "admin_settings":
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        status = "Включен" if MAINTENANCE_MODE else "Выключен"
        markup = types.InlineKeyboardMarkup()
        if MAINTENANCE_MODE:
            markup.add(types.InlineKeyboardButton("Выключить режим", callback_data="admin_maintenance_off"))
        else:
            markup.add(types.InlineKeyboardButton("Включить режим", callback_data="admin_maintenance_on"))
        markup.add(types.InlineKeyboardButton("Изменить причину", callback_data="admin_maintenance_reason"))
        
        bot.send_message(call.message.chat.id, f"НАСТРОЙКИ\n\nРежим обслуживания: {status}\nПричина: {MAINTENANCE_REASON or 'Не указана'}", reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif data in ["admin_maintenance_on", "admin_maintenance_off"]:
        if data == "admin_maintenance_on":
            MAINTENANCE_MODE = True
            MAINTENANCE_REASON = "Технические работы"
            bot.answer_callback_query(call.id, "Режим обслуживания ВКЛЮЧЕН!")
        else:
            MAINTENANCE_MODE = False
            MAINTENANCE_REASON = ""
            bot.answer_callback_query(call.id, "Режим обслуживания ВЫКЛЮЧЕН!")
        
        status = "Включен" if MAINTENANCE_MODE else "Выключен"
        markup = types.InlineKeyboardMarkup()
        if MAINTENANCE_MODE:
            markup.add(types.InlineKeyboardButton("Выключить режим", callback_data="admin_maintenance_off"))
        else:
            markup.add(types.InlineKeyboardButton("Включить режим", callback_data="admin_maintenance_on"))
        markup.add(types.InlineKeyboardButton("Изменить причину", callback_data="admin_maintenance_reason"))
        
        bot.send_message(call.message.chat.id, f"НАСТРОЙКИ\n\nРежим обслуживания: {status}\nПричина: {MAINTENANCE_REASON or 'Не указана'}", reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif data == "admin_maintenance_reason":
        admin_state[user_id] = {"waiting_for_reason": True}
        bot.send_message(call.message.chat.id, "Введите новую причину для режима обслуживания:")
        bot.answer_callback_query(call.id)
    
    elif data == "admin_users":
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT user_id, username, 
            (SELECT COUNT(*) FROM user_ads WHERE user_id = ua.user_id) as ads_count
            FROM user_ads ua 
            ORDER BY ads_count DESC LIMIT 20
        """)
        users = c.fetchall()
        conn.close()
        
        if not users:
            bot.send_message(call.message.chat.id, "Нет пользователей.")
            bot.answer_callback_query(call.id)
            return
        
        text = "Активные пользователи:\n\n"
        for uid, username, ads_count in users:
            text += f"• @{username or uid} - {ads_count} объявлений\n"
        
        bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)
    
    elif data == "admin_broadcast":
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        broadcast_data[user_id] = {"step": "message"}
        bot.send_message(call.message.chat.id, "Введите текст для рассылки:")
        bot.answer_callback_query(call.id)
    
    elif data.startswith("broadcast_"):
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "Нет доступа!")
            return
        
        action = data.replace("broadcast_", "")
        
        if action == "send":
            text = broadcast_data.get(user_id, {}).get("text", "")
            if not text:
                bot.send_message(call.message.chat.id, "Нет текста!")
                return
            
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT DISTINCT user_id FROM user_ads")
            users = c.fetchall()
            conn.close()
            
            success = 0
            for user in users:
                try:
                    bot.send_message(user[0], text)
                    success += 1
                    time.sleep(0.05)
                except:
                    pass
            
            bot.send_message(call.message.chat.id, f"Рассылка завершена! Отправлено: {success}")
            del broadcast_data[user_id]
        elif action == "cancel":
            del broadcast_data[user_id]
            bot.send_message(call.message.chat.id, "Отменено.")
        
        bot.answer_callback_query(call.id)
    
    elif data == "faq":
        text = """
FAQ
----------------------------------------

1. Как подать объявление?
Нажмите "Подать объявление"

2. Сколько ждать модерацию?
До 24 часов

3. Почему отклонили?
- Договорная цена (ЗАПРЕЩЕНА!)
- Нет фото/видео
- Неполное описание

4. Как связаться с продавцом?
По контакту в объявлении

5. Сколько фото/видео?
Фото: до 10, Видео: до 3

6. Что такое подписки?
Вы можете подписаться на категорию и получать уведомления о новых объявлениях.
        """.strip()
        bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)

# ====================== ОБРАБОТЧИК ТЕКСТА ДЛЯ ПРИЧИНЫ ======================
@bot.message_handler(func=lambda m: m.from_user.id in admin_state and admin_state.get(m.from_user.id, {}).get("waiting_for_reason"))
def set_maintenance_reason(message):
    global MAINTENANCE_REASON
    MAINTENANCE_REASON = message.text
    admin_state[message.from_user.id] = {}
    bot.send_message(message.chat.id, f"Причина установлена: {MAINTENANCE_REASON}")
    admin_panel(message)

# ====================== ОБРАБОТЧИК ТЕКСТА ДЛЯ РАССЫЛКИ ======================
@bot.message_handler(func=lambda m: m.from_user.id in broadcast_data and broadcast_data.get(m.from_user.id, {}).get("step") == "message")
def process_broadcast_text(message):
    admin_id = message.from_user.id
    broadcast_data[admin_id]["text"] = message.text
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Отправить", callback_data="broadcast_send"),
        types.InlineKeyboardButton("Отмена", callback_data="broadcast_cancel")
    )
    
    bot.send_message(message.chat.id, 
                    f"Предпросмотр:\n\n{message.text}\n\nОтправить?",
                    reply_markup=markup)

# ====================== ПОДПИСКИ ======================
def show_subscriptions(message):
    user_id = message.from_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, category, ad_type, created_at FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    subs = c.fetchall()
    conn.close()
    
    if not subs:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("СОЗДАТЬ ПОДПИСКУ", callback_data="sub_new"))
        bot.send_message(message.chat.id, "ПОДПИСКИ\n\nУ вас пока нет подписок.", reply_markup=markup)
        return

    for sid, category, ad_type, created_at in subs:
        type_text = ad_type if ad_type else "Любой тип"
        text = f"""
ПОДПИСКА
----------------------------------------

Категория: {category}
Тип: {type_text}
Создана: {created_at}
        """.strip()
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Отписаться", callback_data=f"sub_del_{sid}"))
        bot.send_message(message.chat.id, text, reply_markup=markup)

# ====================== МОИ ОБЪЯВЛЕНИЯ ======================
def show_my_ads(message):
    user_id = message.from_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, price, status, ad_id FROM user_ads WHERE user_id = ? ORDER BY date DESC", (user_id,))
    ads = c.fetchall()
    conn.close()
    
    if not ads:
        bot.send_message(message.chat.id, "МОИ ОБЪЯВЛЕНИЯ\n\nУ вас пока нет объявлений.")
        return
    
    for title, price, status, ad_id in ads:
        status_emoji = "✅" if status == "approved" else "⏳" if status == "pending" else "❌"
        status_text = "Одобрено" if status == "approved" else "На модерации" if status == "pending" else "Отклонено"
        
        text = f"""
МОЕ ОБЪЯВЛЕНИЕ
----------------------------------------

{status_emoji} <b>{title}</b>
Цена: {price} руб
Статус: {status_text}
        """.strip()
        
        if status == "approved":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Удалить", callback_data=f"del_ad_{ad_id}"))
            bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(message.chat.id, text)

# ====================== ПОДДЕРЖКА ======================
def support_menu(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Написать админу", url="https://t.me/Rolexv1n"),
        types.InlineKeyboardButton("FAQ", callback_data="faq")
    )
    bot.send_message(message.chat.id, "ПОДДЕРЖКА\n\nПо всем вопросам обращайтесь к администратору.", reply_markup=markup)

# ====================== АДМИН-ПАНЕЛЬ ======================
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "Нет доступа!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("На модерации", callback_data="admin_moderate"),
        types.InlineKeyboardButton("Одобренные", callback_data="admin_approved"),
        types.InlineKeyboardButton("Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("Управление", callback_data="admin_settings"),
        types.InlineKeyboardButton("Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("Рассылка", callback_data="admin_broadcast")
    )
    
    bot.send_message(message.chat.id, "Админ-панель", reply_markup=markup)

# ====================== ФУНКЦИИ ДЛЯ АДМИН-ПАНЕЛИ ======================
def show_approved_ads(chat_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ad_id, title, user_id, username, date FROM user_ads WHERE status = 'approved' ORDER BY date DESC LIMIT 20")
    ads = c.fetchall()
    conn.close()
    
    if not ads:
        bot.send_message(chat_id, "Нет одобренных объявлений.")
        return
    
    text = "Последние одобренные объявления:\n\n"
    for ad_id, title, user_id, username, date in ads:
        text += f"• {title[:40]} - @{username or user_id}\n"
    
    bot.send_message(chat_id, text)

def publish_to_channel(ad_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM user_ads WHERE ad_id = ?", (ad_id,))
    ad = c.fetchone()
    conn.close()
    
    if not ad:
        return
    
    subcat_text = f"\nПодкатегория: {ad[4]}" if ad[4] else ""
    desc_text = f"\nОписание: {ad[7][:400]}" if ad[7] else ""
    
    channel_text = f"""
НОВОЕ ОБЪЯВЛЕНИЕ
----------------------------------------

{ad[6]}

Категория: {ad[3]}{subcat_text}
Тип: {ad[5]}{desc_text}

Цена: {ad[8]} руб
Контакт: <code>{ad[11]}</code>
Продавец: @{ad[2] or ad[1]}
    """.strip()
    
    try:
        if ad[9]:
            photo_ids = ad[9].split(',')
            bot.send_photo(CHANNEL_ID, photo_ids[0], caption=channel_text, parse_mode='HTML')
        elif ad[10]:
            video_ids = ad[10].split(',')
            bot.send_video(CHANNEL_ID, video_ids[0], caption=channel_text, parse_mode='HTML')
        else:
            bot.send_message(CHANNEL_ID, channel_text, parse_mode='HTML')
    except Exception as e:
        print(f"Ошибка публикации в канал: {e}")

# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    # Устанавливаем вебхук
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL)
    
    print("BLACKBERRY MARKET | 05 ЗАПУЩЕН!")
    print(f"Администраторы: {ADMIN_IDS}")
    print(f"Канал: {CHANNEL_ID}")
    print(f"Webhook: {WEBHOOK_URL}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
